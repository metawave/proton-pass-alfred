# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-05-08

### Fixed
- TOTP action copied the JSON payload instead of just the code, e.g.
  `"totp_uri: 606440 totp: 606440"`. Now returns only the code.
  Thanks @kentrh (#3).
- `pass-cli item view` and `item totp` failed for items whose share or item
  ID starts with `-`: the CLI's argument parser interpreted the value as a
  flag ("error: unexpected argument '-J' found"), so every action on such
  items reported "Could not get password". Switched to the
  `--share-id=<value>` / `--item-id=<value>` form, which binds the value
  directly to the flag.
- Missing `pass-cli` is now surfaced via notification instead of failing
  silently.
- When the vault is locked, the workflow offers a login item instead of
  showing "no results".

### Added
- Documented and tested first-wins behavior for items with multiple TOTP
  entries.

## [1.0.0] - 2026-03-18

- Initial release: Alfred workflow for Proton Pass vault search and copy via
  pass-cli, with multi-vault parallel search, icon caching, clipboard
  auto-clear, and TOTP support.
