package main

import (
	"errors"
	"testing"
)

func TestIsAccountAlreadyExistsError(t *testing.T) {
	cases := []string{
		"browser failed: account already exists",
		"browser complete failed: user_already_exists",
		"auth rejected: user-already-exist",
	}

	for _, tc := range cases {
		if !isAccountAlreadyExistsError(errors.New(tc)) {
			t.Fatalf("expected %q to be classified as account already exists", tc)
		}
	}
}

func TestRegisterFailurePolicyMarksAccountExistsFinal(t *testing.T) {
	status, recoverable, retryable := registerFailurePolicy(errors.New("browser failed: user_already_exists"))

	if status != statusFailedFinal {
		t.Fatalf("status = %q; want %q", status, statusFailedFinal)
	}
	if recoverable || retryable {
		t.Fatalf("recoverable=%v retryable=%v; want both false", recoverable, retryable)
	}
}
