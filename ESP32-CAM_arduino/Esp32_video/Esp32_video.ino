#include <WiFi.h>
#include <HTTPClient.h>
#include "esp_camera.h"

// WiFi 설정
const char* ssid = "3F_es_room1";
const char* password = "0424719222";

// Flask 서버 주소
const char* serverAddress = "http://192.168.31.9:5000/stream";

// 카메라 모듈 설정
#define CAMERA_MODEL_AI_THINKER // 보드 지정 코드
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    15
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5

#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

void setup() {
  Serial.begin(115200);

  // 카메라 모듈 초기화
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;  // LED 컨트롤
  config.ledc_timer = LEDC_TIMER_0; // LED 타이머
  config.pin_d0 = Y2_GPIO_NUM; 
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;  // XCLK 주파수를 20MHz로 설정
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA;  // 카메라 캡처 사이즈를 QVGA로 변경
    config.jpeg_quality = 10;
    config.fb_count = 1;
  } else {
    config.frame_size = FRAMESIZE_VGA;  // 카메라 캡처 사이즈를 QVGA로 변경
    config.jpeg_quality = 10;
    config.fb_count = 2;
  }

  // 카메라 초기화 시 디버깅 메시지 추가
  Serial.println("Initializing camera...");
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    delay(1000);
    ESP.restart();
    return;
  }
  Serial.println("Camera initialized successfully");

  // WiFi 연결
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("WiFi connected");
}

void loop() {
  // 영상 촬영
  camera_fb_t * fb = NULL;
  fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Camera capture failed");
    return;
  }

  // HTTP 클라이언트 초기화
  HTTPClient http;
  http.begin(serverAddress);
  http.addHeader("Content-Type", "image/jpeg");

  // 영상 데이터 전송
  int httpResponseCode = http.POST((uint8_t *)fb->buf, fb->len);
  if (httpResponseCode > 0) {
    Serial.printf("HTTP Response code: %d\n", httpResponseCode);
  } else {
    Serial.printf("HTTP Error code: %s\n", http.errorToString(httpResponseCode).c_str());
  }

  // 메모리 해제
  http.end();
  esp_camera_fb_return(fb);
}
