package main

import "strings"

func isAccountAlreadyExistsError(err error) bool {
	if err == nil {
		return false
	}
	return isAccountAlreadyExistsMessage(err.Error())
}

func isAccountAlreadyExistsMessage(message string) bool {
	normalized := strings.ToLower(message)
	normalized = strings.NewReplacer("_", " ", "-", " ", ".", " ", ":", " ").Replace(normalized)

	return strings.Contains(normalized, "user already exist") ||
		strings.Contains(normalized, "account already exist")
}

func registerFailurePolicy(err error) (status string, recoverable bool, retryable bool) {
	if isAccountAlreadyExistsError(err) {
		return statusFailedFinal, false, false
	}
	return statusFailedRetryable, false, true
}
