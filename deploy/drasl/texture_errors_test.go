package main

import (
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/labstack/echo/v5"
)

func TestOmkTextureValidationStatusDoesNotExposeMessages(t *testing.T) {
	privateMessage := "private-user-error-detail"
	for _, tc := range []struct {
		name string
		err  error
		code int
	}{
		{"bad-request", NewBadRequestUserError(Tr(privateMessage)), http.StatusBadRequest},
		{"forbidden", NewUserErrorWithCode(http.StatusForbidden, Tr(privateMessage)), http.StatusForbidden},
		{"wrapped", fmt.Errorf("wrapped: %w", NewBadRequestUserError(Tr(privateMessage))), http.StatusBadRequest},
		{"rate", NewUserErrorWithCode(http.StatusTooManyRequests, Tr(privateMessage)), http.StatusTooManyRequests},
		{"uncoded", NewUserError(Tr(privateMessage)), http.StatusInternalServerError},
		{"server-error", NewUserErrorWithCode(http.StatusInternalServerError, Tr(privateMessage)), http.StatusInternalServerError},
		{"invalid-code", NewUserErrorWithCode(http.StatusOK, Tr(privateMessage)), http.StatusInternalServerError},
		{"unknown", errors.New(privateMessage), http.StatusInternalServerError},
		{"yggdrasil", &YggdrasilError{Code: http.StatusUnauthorized}, http.StatusUnauthorized},
	} {
		t.Run(tc.name, func(t *testing.T) {
			e := echo.New()
			rec := httptest.NewRecorder()
			c := e.NewContext(httptest.NewRequest(http.MethodPut, "/authlib-injector/fixture", nil), rec)
			app := &App{}
			if err := app.HandleYggdrasilError(tc.err, c); err != nil {
				t.Fatal(err)
			}
			if rec.Code != tc.code {
				t.Fatalf("expected status %d, got %d", tc.code, rec.Code)
			}
			if strings.Contains(rec.Body.String(), privateMessage) {
				t.Fatal("private validation detail appeared in response")
			}
		})
	}
}
