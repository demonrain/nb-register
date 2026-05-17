package app

import "testing"

func TestNormalizeGoPayAddBalanceModeRekberinaja(t *testing.T) {
	for _, value := range []string{"rekberinaja", "R", "r_platform", "r-platform", "r platform"} {
		if got := normalizeGoPayAddBalanceMode(value); got != "rekberinaja" {
			t.Fatalf("normalizeGoPayAddBalanceMode(%q) = %q", value, got)
		}
	}
}

func TestDefaultGoPayAddBalanceRekberinaja(t *testing.T) {
	addBalance := defaultGoPayAddBalance(orchestratorConfig{
		GoPayAddBalanceMode:                    "r_platform",
		GoPayAddBalanceRekberinajaEndpoint:     "https://example.invalid/checkout",
		GoPayAddBalanceRekberinajaToken:        "token",
		GoPayAddBalanceRekberinajaDeviceID:     "device",
		GoPayAddBalanceRekberinajaStore:        "store",
		GoPayAddBalanceRekberinajaProductID:    "product",
		GoPayAddBalanceRekberinajaServiceID:    "service",
		GoPayAddBalanceRekberinajaPayment:      "saldo",
		GoPayAddBalanceRekberinajaEmail:        "invoice@example.invalid",
		GoPayAddBalanceRekberinajaPromoCode:    "promo",
		GoPayAddBalanceRekberinajaUsePoin:      true,
		GoPayAddBalanceRekberinajaUserAgent:    "agent",
		GoPayAddBalanceRekberinajaOrigin:       "https://origin.example.invalid",
		GoPayAddBalanceRekberinajaReferer:      "https://referer.example.invalid/",
		GoPayAddBalanceRekberinajaRefresh:      "refresh",
		GoPayAddBalanceRekberinajaFeeTotal:     1400,
		GoPayAddBalanceRekberinajaPollTimeout:  90,
		GoPayAddBalanceRekberinajaPollInterval: 3,
	})
	rekberinaja := addBalance.GetRekberinaja()
	if rekberinaja == nil {
		t.Fatalf("defaultGoPayAddBalance did not return rekberinaja method: %#v", addBalance)
	}
	if rekberinaja.GetEndpointUrl() != "https://example.invalid/checkout" ||
		rekberinaja.GetBearerToken() != "token" ||
		rekberinaja.GetDeviceId() != "device" ||
		rekberinaja.GetStore() != "store" ||
		rekberinaja.GetProductId() != "product" ||
		rekberinaja.GetServiceId() != "service" ||
		rekberinaja.GetPaymentMethod() != "saldo" ||
		rekberinaja.GetInvoiceEmail() != "invoice@example.invalid" ||
		rekberinaja.GetPromoCode() != "promo" ||
		!rekberinaja.GetUsePoin() ||
		rekberinaja.GetUserAgent() != "agent" ||
		rekberinaja.GetOrigin() != "https://origin.example.invalid" ||
		rekberinaja.GetReferer() != "https://referer.example.invalid/" ||
		rekberinaja.GetRefreshToken() != "refresh" ||
		rekberinaja.GetFeeTotal() != 1400 ||
		rekberinaja.GetPollTimeoutSeconds() != 90 ||
		rekberinaja.GetPollIntervalSeconds() != 3 {
		t.Fatalf("rekberinaja config mismatch: %+v", rekberinaja)
	}
}
