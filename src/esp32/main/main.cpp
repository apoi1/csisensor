/*
 * WiFi CSI → MQTT streamer for ESP32-S3 (ESP-IDF v5.x)
 *
 * Pipeline:
 *   WiFi STA → native ESP-IDF CSI callback → FreeRTOS queue
 *            → publisher task → MQTT broker (Mosquitto on the LAN)
 *
 * A lwIP ping session (default 10 Hz, USE_TRAFFIC_PING) keeps packets
 * flowing to the STA so CSI callbacks fire at a steady sample rate.
 *
 * MQTT payload (topic esp32/<device-id>/csi/raw), ASCII CSV:
 *   t_us,rssi,n,seq,a0,a1,...,a<n-1>
 * where a* are per-subcarrier amplitudes = round(sqrt(I^2 + Q^2)).
 *
 * NOTE: ESP-IDF ships the CSI API natively (esp_wifi_set_csi_rx_cb);
 * no external component or repo is required.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <assert.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

#include "esp_log.h"
#include "esp_timer.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "esp_mac.h"
#include "nvs_flash.h"
#include "mqtt_client.h"

#include "lwip/ip4_addr.h"
#if USE_TRAFFIC_PING
#include "ping/ping_sock.h"
#endif

#include "config.h"

static const char *TAG = "csi_main";

#define SAMPLE_QUEUE_DEPTH 32

typedef struct {
    uint64_t t_us;                     /* device timestamp (µs)            */
    int8_t   rssi;                     /* dBm                               */
    uint16_t n;                        /* subcarrier count                  */
    uint32_t seq;                      /* monotonic sequence number         */
    uint8_t  amp[CSI_MAX_SUBCARRIERS]; /* sqrt(I²+Q²), fits in uint8        */
} csi_sample_t;

static QueueHandle_t           s_sample_queue;
static esp_mqtt_client_handle_t s_mqtt;
#if USE_TRAFFIC_PING
static esp_ping_session_t      *s_ping;
#endif

static volatile uint32_t s_captured;
static volatile uint32_t s_qfull;
static volatile uint32_t s_published;
static volatile uint32_t s_publish_failed;

/* ============================================================ CSI ====== */

extern "C" void wifi_csi_rx_cb(void *ctx, wifi_csi_info_t *info)
{
    (void)ctx;
    if (info == NULL || info->csi_buf == NULL) {
        return;
    }

    uint16_t n = info->csi_len / 2;            /* csi_len is bytes (I/Q pairs) */
    if (n > CSI_MAX_SUBCARRIERS) {
        n = CSI_MAX_SUBCARRIERS;
    }

    csi_sample_t s = {};
    s.t_us = (uint64_t)esp_timer_get_time();
    s.rssi = (int8_t)info->rx_ctrl.rssi;
    s.n    = n;
    s.seq  = s_captured++;

    for (uint16_t i = 0; i < n; i++) {
        const float re  = (float)info->csi_buf[2 * i];
        const float im  = (float)info->csi_buf[2 * i + 1];
        const float mag = sqrtf(re * re + im * im);
        s.amp[i] = (uint8_t)(mag + 0.5f);    /* |I|,|Q| ≤ 127 → mag ≤ ~180 */
    }

    /* The CSI callback runs in the WiFi task: never block, only enqueue. */
    if (xQueueSend(s_sample_queue, &s, 0) != pdTRUE) {
        s_qfull++;
    }
}

/* ===================================================== MQTT publish ==== */

static void publisher_task(void *arg)
{
    (void)arg;
    const size_t buf_len = 64 + (size_t)CSI_MAX_SUBCARRIERS * 4;
    char *buf = (char *)malloc(buf_len);
    if (buf == NULL) {
        ESP_LOGE(TAG, "payload buffer alloc failed");
        vTaskDelete(NULL);
        return;
    }

    /* Per-device topic: esp32/<last-3-MAC-bytes>/csi/raw (eFuse-derived
     * id, stable across reboots) so several ESP32s never collide on the
     * broker; the backend routes each device to its own DSP pipeline. */
    char topic_csi[48];
    uint8_t mac[6] = {0};
    if (esp_read_mac(mac, ESP_MAC_WIFI_STA) != ESP_OK) {
        /* Review finding R3-13: never trust an unchecked return - a zero
         * id still yields a valid, unique-ish topic instead of garbage. */
        ESP_LOGE(TAG, "esp_read_mac failed; using zero device id");
    }
    snprintf(topic_csi, sizeof(topic_csi), "%s/%02x%02x%02x/csi/raw",
             MQTT_TOPIC_PREFIX, mac[3], mac[4], mac[5]);
    ESP_LOGI(TAG, "publishing CSI to topic %s", topic_csi);

    csi_sample_t s;
    while (true) {
        if (xQueueReceive(s_sample_queue, &s, portMAX_DELAY) != pdTRUE) {
            continue;
        }

        int off = snprintf(buf, buf_len, "%llu,%d,%u,%u",
                           (unsigned long long)s.t_us,
                           (int)s.rssi, (unsigned)s.n, (unsigned)s.seq);
        for (uint16_t i = 0; i < s.n && off > 0 && (size_t)off < buf_len - 1; i++) {
            off += snprintf(buf + off, buf_len - (size_t)off, ",%u",
                             (unsigned)s.amp[i]);
        }

        if (off > 0 && esp_mqtt_client_publish(s_mqtt, topic_csi, buf,
                                               off, 0, 0) >= 0) {
            s_published++;
        } else {
            s_publish_failed++;
        }
    }
}

static void stats_task(void *arg)
{
    (void)arg;
    while (true) {
        ESP_LOGI(TAG, "csi: captured=%u qfull=%u published=%u failed=%u",
                 (unsigned)s_captured, (unsigned)s_qfull,
                 (unsigned)s_published, (unsigned)s_publish_failed);
        vTaskDelay(pdMS_TO_TICKS(10000));
    }
}

/* ================================================= MQTT / events ======= */

static void mqtt_event_cb(void *handler_args, esp_event_base_t base,
                          int32_t event_id, void *event_data)
{
    (void)handler_args;
    (void)base;
    const esp_mqtt_event_handle_t event = (const esp_mqtt_event_handle_t)event_data;
    switch (event->event_id) {
    case MQTT_EVENT_CONNECTED:
        ESP_LOGI(TAG, "MQTT connected");
        break;
    case MQTT_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "MQTT disconnected (auto-reconnect)");
        break;
    default:
        break;
    }
}

static void mqtt_start(void)
{
    if (s_mqtt != NULL) {
        return;
    }
    esp_mqtt_client_config_t cfg = {};
    cfg.broker.address.uri = MQTT_BROKER_URI;
    cfg.session.keepalive   = 30;

    s_mqtt = esp_mqtt_client_init(&cfg);
    assert(s_mqtt != NULL);
    esp_mqtt_client_register_event(s_mqtt, ESP_EVENT_ANY_ID, mqtt_event_cb, NULL);
    esp_mqtt_client_start(s_mqtt);
    ESP_LOGI(TAG, "MQTT client started → %s", MQTT_BROKER_URI);
}

#if USE_TRAFFIC_PING
/* Steady ICMP echo to the gateway: every reply received by the STA
 * triggers a CSI callback → regular ~10 Hz sampling.                     */
static void start_traffic_ping(const esp_netif_ip_info_t *ip_info)
{
    if (s_ping != NULL) {
        return;
    }
    esp_ping_config_t ping_cfg = {};
    IP4_ADDR(&ping_cfg.target_addr.u_addr.ip4,
             ip4_addr1(&ip_info->gw), ip4_addr2(&ip_info->gw),
             ip4_addr3(&ip_info->gw), ip4_addr4(&ip_info->gw));
    ping_cfg.target_addr.type = IPADDR_TYPE_V4;
    ping_cfg.count            = 0;        /* endless */
    ping_cfg.interval_ms      = CSI_INTERVAL_MS;
    ping_cfg.timeout_ms       = 1000;
    ping_cfg.data_size        = 32;

    if (esp_ping_new_session(&ping_cfg, NULL, &s_ping) == ESP_OK && s_ping != NULL) {
        esp_ping_start(s_ping);
        ESP_LOGI(TAG, "traffic ping to gateway started (every %d ms)",
                 CSI_INTERVAL_MS);
    } else {
        ESP_LOGW(TAG, "ping session failed — ping the ESP32 externally "
                      "(see DEPLOYMENT.md)");
    }
}
#endif

static void wifi_event_handler(void *arg, esp_event_base_t base,
                               int32_t event_id, void *event_data)
{
    (void)arg;
    if (base == WIFI_EVENT) {
        switch (event_id) {
        case WIFI_EVENT_STA_START:
            esp_wifi_connect();
            break;
        case WIFI_EVENT_STA_DISCONNECTED:
            ESP_LOGW(TAG, "WiFi disconnected — reconnecting");
            esp_wifi_connect();
            break;
        default:
            break;
        }
    } else if (base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        const ip_event_got_ip_t *event = (const ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "WiFi connected, IP: " IPSTR, IP2STR(&event->ip_info.ip));
        mqtt_start();
#if USE_TRAFFIC_PING
        start_traffic_ping(&event->ip_info);
#else
        ESP_LOGW(TAG, "traffic ping disabled — generate traffic externally "
                      "(see DEPLOYMENT.md)");
#endif
    }
}

/* ========================================================== app_main === */

extern "C" void app_main(void)
{
    ESP_LOGI(TAG, "ESP32-S3 WiFi-CSI firmware booting");

    s_sample_queue = xQueueCreate(SAMPLE_QUEUE_DEPTH, sizeof(csi_sample_t));
    assert(s_sample_queue != NULL);

    /* NVS (required by WiFi driver) */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }

    /* Network + WiFi STA */
    esp_netif_init();
    esp_event_loop_create_default();
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t wifi_cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi_cfg));

    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                               wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                                               wifi_event_handler, NULL));

    wifi_config_t sta_cfg = {};
    strlcpy((char *)sta_cfg.sta.ssid, WIFI_SSID, sizeof(sta_cfg.sta.ssid));
    strlcpy((char *)sta_cfg.sta.password, WIFI_PASS, sizeof(sta_cfg.sta.password));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &sta_cfg));
    ESP_ERROR_CHECK(esp_wifi_start());

    /* Native CSI capture (ESP-IDF API — no external component needed) */
    wifi_csi_config_t csi_cfg = {};
    csi_cfg.lltf_en           = true;
    csi_cfg.htltf_en          = true;
    csi_cfg.stbc_htltf2_en    = true;
    csi_cfg.ltf_merge_en      = true;
    csi_cfg.channel_filter_en = CSI_CHANNEL_FILTER;
    csi_cfg.manu_scale        = false;
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi_cfg));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(wifi_csi_rx_cb, NULL));
    ESP_LOGI(TAG, "CSI capture registered");

    xTaskCreate(publisher_task, "csi_pub",   4096, NULL, 5, NULL);
    xTaskCreate(stats_task,     "csi_stats", 2048, NULL, 4, NULL);
}
