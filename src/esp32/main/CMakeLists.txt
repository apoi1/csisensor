idf_component_register(
    SRCS "main.cpp"
    INCLUDE_DIRS "."
    PRIV_REQUIRES nvs_flash esp_wifi esp_event esp_netif mqtt lwip esp_timer
)
