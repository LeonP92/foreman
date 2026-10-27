# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Unreleased

### Added

- Skills: `setup`, `review`, `verify`, `diagram` and `audit`.
- CLI commands for graphing, rule checks, config checks, rendering, mapping and browser runs.
- Interactive diagram view of a change and codebase map view (dependency-ordered, with a matrix and smells).

### Known limits

- Templates and markup files aren't graphed: the diagram skill adds template nodes and
  their edges by hand, and the map leaves them out of the import graph. Full template
  graphing is planned.
