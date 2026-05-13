package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestExtractOTPFromPayload(t *testing.T) {
	now := time.Now().Unix()
	payload := map[string]any{
		"source":    "whatsapp",
		"timestamp": now,
		"message":   "GoPay verification code: 1234. Do not share it.",
	}
	code, ts := extractOTPFromPayload(payload)
	if code != "1234" {
		t.Fatalf("code = %q, want 1234", code)
	}
	if ts != now {
		t.Fatalf("ts = %d, want %d", ts, now)
	}
}

func TestStoreWaitHonorsIssuedAfter(t *testing.T) {
	store := newOTPStore(10, 600)
	now := time.Now().Unix()
	if err := store.submit("1111", "whatsapp", "", now-10, "gopay"); err != nil {
		t.Fatal(err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer cancel()
	if item, ok := store.wait(ctx, "gopay", 30*time.Millisecond, now-5); ok {
		t.Fatalf("unexpected old item: %+v", item)
	}

	if err := store.submit("2222", "whatsapp", "", now, "gopay"); err != nil {
		t.Fatal(err)
	}
	ctx, cancel = context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	item, ok := store.wait(ctx, "gopay", time.Second, now-5)
	if !ok {
		t.Fatal("expected new otp")
	}
	if item.OTP != "2222" {
		t.Fatalf("otp = %q, want 2222", item.OTP)
	}
}

func TestPurposeMismatchKeepsItem(t *testing.T) {
	store := newOTPStore(10, 600)
	if err := store.submit("3333", "outlook", "email", time.Now().Unix(), "email code"); err != nil {
		t.Fatal(err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer cancel()
	if item, ok := store.wait(ctx, "gopay", 30*time.Millisecond, 0); ok {
		t.Fatalf("unexpected gopay item: %+v", item)
	}

	ctx, cancel = context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	item, ok := store.wait(ctx, "any", time.Second, 0)
	if !ok || item.OTP != "3333" {
		t.Fatalf("any wait = (%+v, %v), want 3333 true", item, ok)
	}
}

func TestHTTPSubmitAndWait(t *testing.T) {
	store := newOTPStore(10, 600)
	handler := newHTTPHandler(store, map[string]bool{"/webhook/otp": true})
	body := `{"source":"whatsapp","notification":"Your GoPay OTP is 4444"}`
	req := httptest.NewRequest(http.MethodPost, "/webhook/otp", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d body=%s", rec.Code, rec.Body.String())
	}

	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	item, ok := store.wait(ctx, "gopay", time.Second, time.Now().Unix()-5)
	if !ok || item.OTP != "4444" {
		t.Fatalf("wait = (%+v, %v), want 4444 true", item, ok)
	}
}
