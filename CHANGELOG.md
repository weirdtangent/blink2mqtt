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
