package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/labstack/echo/v5"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

func omkDB(t *testing.T) *gorm.DB {
	t.Helper()
	db, err := gorm.Open(sqlite.Open(filepath.Join(t.TempDir(), "state.db")), &gorm.Config{Logger: logger.Default.LogMode(logger.Silent)})
	if err != nil {
		t.Fatal(err)
	}
	sql, _ := db.DB()
	t.Cleanup(func() { sql.Close() })
	for _, query := range []string{
		"CREATE TABLE clients (uuid TEXT PRIMARY KEY, user_uuid TEXT, player_uuid TEXT, version INTEGER, last_used_at DATETIME)",
		"CREATE TABLE players (uuid TEXT PRIMARY KEY, user_uuid TEXT, server_id TEXT)",
		"INSERT INTO clients VALUES ('client', 'owner', 'player', 0, NULL), ('other-client','other','other-player',0,NULL)",
		"INSERT INTO players VALUES ('player','owner','approval'), ('other-player','other','other-approval')",
	} {
		if err := db.Exec(query).Error; err != nil {
			t.Fatal(err)
		}
	}
	return db
}

func TestOmkRevocationClearsOnlyOwnedApprovals(t *testing.T) {
	db := omkDB(t)
	app := &App{}
	if err := db.Transaction(func(tx *gorm.DB) error { return app.InvalidateUser(tx, &User{UUID: "owner"}) }); err != nil {
		t.Fatal(err)
	}
	var owned, other int
	db.Raw("SELECT COUNT(*) FROM players WHERE user_uuid='owner' AND server_id IS NOT NULL").Scan(&owned)
	db.Raw("SELECT COUNT(*) FROM players WHERE user_uuid='other' AND server_id='other-approval'").Scan(&other)
	if owned != 0 || other != 1 {
		t.Fatal("approval invalidation crossed account boundaries")
	}
	stale := &Client{UUID: "client", Version: 0, LastUsedAt: time.Now()}
	if recordClientUse(db, stale) == nil {
		t.Fatal("stale usage write was accepted")
	}
	var version int
	db.Raw("SELECT version FROM clients WHERE uuid='client'").Scan(&version)
	if version != 1 {
		t.Fatal("usage write resurrected revoked version")
	}
	stale.Version = 1
	if err := recordClientUse(db, stale); err != nil {
		t.Fatal(err)
	}
	if err := app.InvalidatePlayer(db, &Player{UUID: "other-player"}); err != nil {
		t.Fatal(err)
	}
	db.Raw("SELECT COUNT(*) FROM players WHERE server_id IS NOT NULL").Scan(&other)
	if other != 0 {
		t.Fatal("profile approval survived invalidation")
	}
}

func TestOmkSecurityRequestsAreSerialized(t *testing.T) {
	app := &App{}
	e := echo.New()
	e.Use(app.serializeSecurityRequests())
	var active, maximum atomic.Int32
	e.POST("/operation", func(c *echo.Context) error {
		count := active.Add(1)
		for old := maximum.Load(); count > old && !maximum.CompareAndSwap(old, count); old = maximum.Load() {
		}
		time.Sleep(time.Millisecond)
		active.Add(-1)
		return c.NoContent(http.StatusNoContent)
	})
	var group sync.WaitGroup
	for i := 0; i < 24; i++ {
		group.Add(1)
		go func() {
			defer group.Done()
			rec := httptest.NewRecorder()
			e.ServeHTTP(rec, httptest.NewRequest(http.MethodPost, "/operation", strings.NewReader("{}")))
			if rec.Code != 204 {
				t.Error("unexpected response")
			}
		}()
	}
	group.Wait()
	if maximum.Load() != 1 {
		t.Fatal("security operations overlapped")
	}
}

type omkSlowBody struct {
	entered chan struct{}
	release chan struct{}
	once    sync.Once
}

func (r *omkSlowBody) Read(p []byte) (int, error) {
	r.once.Do(func() { close(r.entered) })
	<-r.release
	return 0, io.EOF
}
func (r *omkSlowBody) Close() error { return nil }

func TestOmkSlowBodyDoesNotHoldSecurityBoundary(t *testing.T) {
	app := &App{}
	e := echo.New()
	e.Use(app.serializeSecurityRequests())
	e.POST("/operation", func(c *echo.Context) error { return c.NoContent(http.StatusNoContent) })
	slow := &omkSlowBody{entered: make(chan struct{}), release: make(chan struct{})}
	first := httptest.NewRequest(http.MethodPost, "/operation", nil)
	first.Body = slow
	done := make(chan struct{})
	go func() { e.ServeHTTP(httptest.NewRecorder(), first); close(done) }()
	<-slow.entered
	fast := make(chan struct{})
	go func() {
		e.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest(http.MethodPost, "/operation", strings.NewReader("{}")))
		close(fast)
	}()
	select {
	case <-fast:
	case <-time.After(2 * time.Second):
		close(slow.release)
		t.Fatal("slow upload blocked security operations")
	}
	close(slow.release)
	<-done
}
