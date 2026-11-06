# syntax=docker/dockerfile:1.7
# Drasl owns authentication; local patches enforce invite and revocation boundaries.
FROM golang:1.26.4@sha256:f96cc555eb8db430159a3aa6797cd5bae561945b7b0fe7d0e284c63a3b291609 AS builder
WORKDIR /src
ADD --checksum=sha256:cc6196dbd538e6e17d3d22d180697673b607f585603f4ee72cebeb4dff615493 https://codeload.github.com/unmojang/drasl/tar.gz/0fe488c087bbe792485e9c5dae751c6e5fbdc380 /tmp/drasl.tar.gz
RUN tar -xzf /tmp/drasl.tar.gz --strip-components=1 -C /src
COPY one-use-invites.patch /tmp/one-use-invites.patch
RUN git apply --check /tmp/one-use-invites.patch && git apply /tmp/one-use-invites.patch
COPY session-revocation.patch /tmp/session-revocation.patch
RUN git apply --check /tmp/session-revocation.patch && git apply /tmp/session-revocation.patch
COPY revocation_test.go /src/omk_security_test.go
RUN --mount=type=cache,target=/go/pkg/mod go mod download
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build gofmt -w omk_security.go omk_security_test.go main.go model.go player.go user.go session.go && go test -mod=readonly -run '^TestOmk' -count=1 .
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build CGO_ENABLED=1 go build -mod=readonly -tags netgo,osusergo -trimpath -ldflags="-linkmode external -extldflags=-static" -o /out/drasl .

# Reuse the pinned upstream assets, certificates and default skin configuration.
FROM unmojang/drasl:4.0.0@sha256:d02f57bda0f0840ab6a2d6c9e167b923c71d4c7d7c9ef322c8ffce44854df6ad
COPY --from=builder /out/drasl /usr/local/bin/omk-drasl
COPY --from=builder /src/LICENSE /usr/local/share/licenses/drasl/LICENSE
COPY one-use-invites.patch /usr/local/share/drasl/patches/one-use-invites.patch
COPY session-revocation.patch /usr/local/share/drasl/patches/session-revocation.patch
COPY revocation_test.go /usr/local/share/drasl/patches/revocation_test.go
ENV DRASL_DEFAULT_DATA_DIRECTORY=/nix/store/5b56b5cnw98xaa8bahz1ghsvk3k8lvhz-drasl-4.0.0/share/drasl
LABEL org.opencontainers.image.title="Drasl 4.0.0 with OmkalityCraft invitation and revocation fixes" \
      org.opencontainers.image.source="https://github.com/omkality/omkalitycraft" \
      org.opencontainers.image.version="4.0.0-omk.2" \
      org.opencontainers.image.licenses="GPL-3.0-only"
CMD ["/usr/local/bin/omk-drasl"]
