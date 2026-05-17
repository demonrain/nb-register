package activities

import (
	"testing"
	"time"
)

func TestRekberinajaPaymentPhone(t *testing.T) {
	tests := []struct {
		name string
		in   string
		want string
	}{
		{name: "local without leading zero", in: "81234567890", want: "081234567890"},
		{name: "local with leading zero", in: "081234567890", want: "081234567890"},
		{name: "country code", in: "6281234567890", want: "081234567890"},
		{name: "plus country code", in: "+62 812-3456-7890", want: "081234567890"},
		{name: "empty", in: "", want: ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := rekberinajaPaymentPhone(tt.in); got != tt.want {
				t.Fatalf("rekberinajaPaymentPhone(%q) = %q, want %q", tt.in, got, tt.want)
			}
		})
	}
}

func TestRekberinajaCheckoutURL(t *testing.T) {
	now := time.UnixMilli(1779001331284)
	got, err := rekberinajaURLWithCacheBuster("https://api.rekberinaja.com/api/transaction/product/checkout", now)
	if err != nil {
		t.Fatalf("rekberinajaURLWithCacheBuster returned error: %v", err)
	}
	want := "https://api.rekberinaja.com/api/transaction/product/checkout?_=1779001331284"
	if got != want {
		t.Fatalf("rekberinajaURLWithCacheBuster = %q, want %q", got, want)
	}

	got, err = rekberinajaURLWithCacheBuster("https://api.rekberinaja.com/api/transaction/product/checkout?_=1&foo=bar", now)
	if err != nil {
		t.Fatalf("rekberinajaURLWithCacheBuster with existing query returned error: %v", err)
	}
	want = "https://api.rekberinaja.com/api/transaction/product/checkout?_=1&foo=bar"
	if got != want {
		t.Fatalf("rekberinajaURLWithCacheBuster with existing query = %q, want %q", got, want)
	}
}

func TestRekberinajaAPIBaseURL(t *testing.T) {
	got, err := rekberinajaAPIBaseURL("https://api.rekberinaja.com/api/transaction/product/checkout?_=1779001331284")
	if err != nil {
		t.Fatalf("rekberinajaAPIBaseURL returned error: %v", err)
	}
	if got != "https://api.rekberinaja.com/api" {
		t.Fatalf("rekberinajaAPIBaseURL = %q", got)
	}
}
