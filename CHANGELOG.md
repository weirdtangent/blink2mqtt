## [2.5.3](https://github.com/weirdtangent/blink2mqtt/compare/v2.5.2...v2.5.3) (2026-02-15)


### Bug Fixes

* only trigger Claude review on [@claude](https://github.com/claude) mention ([6d67e4b](https://github.com/weirdtangent/blink2mqtt/commit/6d67e4b0709118e1365f2f605d587a7ca7ceeb12))

## [2.5.2](https://github.com/weirdtangent/blink2mqtt/compare/v2.5.1...v2.5.2) (2026-02-15)


### Bug Fixes

* add checkout step to claude-code-review workflow ([8d468fa](https://github.com/weirdtangent/blink2mqtt/commit/8d468fa7f749727ddb0ec4574c80dca90ea3f18d))

## [2.5.1](https://github.com/weirdtangent/blink2mqtt/compare/v2.5.0...v2.5.1) (2026-02-15)


### Bug Fixes

* add id-token: write permission for claude-code-action ([edc26ff](https://github.com/weirdtangent/blink2mqtt/commit/edc26fff5cdaefd9ae1575b9f71877110ba1f48c))

# [2.5.0](https://github.com/weirdtangent/blink2mqtt/compare/v2.4.3...v2.5.0) (2026-02-14)


### Bug Fixes

* address review feedback for vision request ([4dee2a0](https://github.com/weirdtangent/blink2mqtt/commit/4dee2a0e9a0ae21ebc9e5c3ab6192444ecbb866d))


### Features

* publish vision request on motion events ([a826512](https://github.com/weirdtangent/blink2mqtt/commit/a8265123fcc7e7f121b7ac5a4e2de6acd6675b99))

## [2.4.3](https://github.com/weirdtangent/blink2mqtt/compare/v2.4.2...v2.4.3) (2026-02-06)


### Bug Fixes

* upgrade pip in Docker build to patch CVE-2026-1703 ([5e39cee](https://github.com/weirdtangent/blink2mqtt/commit/5e39ceeaba38dc6c6b8ef1425b9bfc26b45cf173))

## [2.4.2](https://github.com/weirdtangent/blink2mqtt/compare/v2.4.1...v2.4.2) (2026-02-05)


### Bug Fixes

* resolve missing camera entities and broken API call tracking ([f0bf5f5](https://github.com/weirdtangent/blink2mqtt/commit/f0bf5f57cebc23ef1c3f70f14d95e4b068426cd2))

## [2.4.1](https://github.com/weirdtangent/blink2mqtt/compare/v2.4.0...v2.4.1) (2026-01-19)


### Bug Fixes

* remove duplicate CVE-2024-52005 entry in .trivyignore ([9a2aaf0](https://github.com/weirdtangent/blink2mqtt/commit/9a2aaf0e89dc4a66ff404bdd8a684732cc6492f0))

# [2.4.0](https://github.com/weirdtangent/blink2mqtt/compare/v2.3.0...v2.4.0) (2026-01-06)


### Bug Fixes

* ensure protocol_version is always string type ([a9fc2d4](https://github.com/weirdtangent/blink2mqtt/commit/a9fc2d4237caf2dc981ae46673c168281dfe6df3))


### Features

* add configurable MQTT protocol version support ([9e22bb5](https://github.com/weirdtangent/blink2mqtt/commit/9e22bb55f3407fb42d8c5f83b675b8d5fdd136e3)), closes [#13](https://github.com/weirdtangent/blink2mqtt/issues/13)

# [2.3.0](https://github.com/weirdtangent/blink2mqtt/compare/v2.2.3...v2.3.0) (2025-12-23)


### Features

* add security workflow features ([2bda58e](https://github.com/weirdtangent/blink2mqtt/commit/2bda58e92c51776fe607429ad4fc203e0864dfb4))

## [2.2.3](https://github.com/weirdtangent/blink2mqtt/compare/v2.2.2...v2.2.3) (2025-11-24)


### Bug Fixes

* make sure all device_names logged are in quotes ([b23367e](https://github.com/weirdtangent/blink2mqtt/commit/b23367e3d232095ca7922f96e1c31cbd67151fc1))

## [2.2.2](https://github.com/weirdtangent/blink2mqtt/compare/v2.2.1...v2.2.2) (2025-11-24)


### Bug Fixes

* always try to log device_name in preference to device_id ([9aa22d2](https://github.com/weirdtangent/blink2mqtt/commit/9aa22d2bad815b75e4a24797fea6bae302f059d7))

## [2.2.1](https://github.com/weirdtangent/blink2mqtt/compare/v2.2.0...v2.2.1) (2025-11-09)


### Bug Fixes

* fix interval setting ([8d1a8c3](https://github.com/weirdtangent/blink2mqtt/commit/8d1a8c3dd5cdca9a21ab094d2073e263eb8e77ec))

# [2.2.0](https://github.com/weirdtangent/blink2mqtt/compare/v2.1.0...v2.2.0) (2025-11-08)


### Features

* **mqtt:** migrate Blink devices and service discovery to new 2024 “device” schema ([b72d25e](https://github.com/weirdtangent/blink2mqtt/commit/b72d25e8f9994172906627fc72114ecf745c1458))

# [2.1.0](https://github.com/weirdtangent/blink2mqtt/compare/v2.0.8...v2.1.0) (2025-11-08)


### Features

* refactor discovery for HA mqtt device type ([19e2665](https://github.com/weirdtangent/blink2mqtt/commit/19e2665efb763d13dd4d50878450b9d024dfa0ed))

## [2.0.8](https://github.com/weirdtangent/blink2mqtt/compare/v2.0.7...v2.0.8) (2025-10-29)


### Bug Fixes

* more adjustments, they never end ([1b4bb03](https://github.com/weirdtangent/blink2mqtt/commit/1b4bb037be20f70b7d26a1715704f373ec045ac3))

## [2.0.7](https://github.com/weirdtangent/blink2mqtt/compare/v2.0.6...v2.0.7) (2025-10-29)


### Bug Fixes

* not dev_id, but component_type ([99e4d72](https://github.com/weirdtangent/blink2mqtt/commit/99e4d72e196457a22b7d7ff2e3d302ee4ea366d9))

## [2.0.6](https://github.com/weirdtangent/blink2mqtt/compare/v2.0.5...v2.0.6) (2025-10-29)


### Bug Fixes

* no, we need to construct the disc_topic ([9cc1c51](https://github.com/weirdtangent/blink2mqtt/commit/9cc1c519bc504b32c66a88e391df441484f7b831))

## [2.0.5](https://github.com/weirdtangent/blink2mqtt/compare/v2.0.4...v2.0.5) (2025-10-29)


### Bug Fixes

* use 'service' for main service entity ([7f57faf](https://github.com/weirdtangent/blink2mqtt/commit/7f57faf2d157a7a7277d1e8eae8abce58da186ee))

## [2.0.4](https://github.com/weirdtangent/blink2mqtt/compare/v2.0.3...v2.0.4) (2025-10-29)


### Bug Fixes

* fix service_slug, disc_t calls ([d818625](https://github.com/weirdtangent/blink2mqtt/commit/d81862521005919a9109cbc74e1d6f306c3826ea))

## [2.0.3](https://github.com/weirdtangent/blink2mqtt/compare/v2.0.2...v2.0.3) (2025-10-28)


### Bug Fixes

* name and edentifier of device were switched ([121f1d5](https://github.com/weirdtangent/blink2mqtt/commit/121f1d54f8061761d022151d53d73e8dcffbe427))

## [2.0.2](https://github.com/weirdtangent/blink2mqtt/compare/v2.0.1...v2.0.2) (2025-10-27)


### Bug Fixes

* add apt-update to Dockerfile and also pull latest in github action ([f4f7d2a](https://github.com/weirdtangent/blink2mqtt/commit/f4f7d2a3cf6c86c5eff4c2df66b7a71b8702756a))

## [2.0.1](https://github.com/weirdtangent/blink2mqtt/compare/v2.0.0...v2.0.1) (2025-10-25)


### Bug Fixes

* cleanup 3 interval timers: config, controls, cmd topic, update ([8aa4667](https://github.com/weirdtangent/blink2mqtt/commit/8aa4667533e21d7b4da6ee20d8ef9e57243b7be3))

# [2.0.0](https://github.com/weirdtangent/blink2mqtt/compare/v1.0.1...v2.0.0) (2025-10-25)


* feat!: prepare v2 release ([4e051c1](https://github.com/weirdtangent/blink2mqtt/commit/4e051c1929456b79faf2cf222bdb37ca9b6f7352))


### BREAKING CHANGES

* async control & payload shape changed; HA rediscovery may be required.

## [1.0.1](https://github.com/weirdtangent/blink2mqtt/compare/v1.0.0...v1.0.1) (2025-10-09)


### Bug Fixes

* tls_set call for ssl mqtt connections ([1b7ee8e](https://github.com/weirdtangent/blink2mqtt/commit/1b7ee8e5a72c8e506cd1940f57fddb7f1baeab5c))

# 1.0.0 (2025-10-09)


### Features

* semantic versioning, github action features, writes a version file, and tags Docker images ([48f6fa1](https://github.com/weirdtangent/blink2mqtt/commit/48f6fa1c8c429bf7c1cbb3d4466a9db221c53e20))
