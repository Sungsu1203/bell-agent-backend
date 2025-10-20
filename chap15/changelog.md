## [2025-10-11] Logging Unification & Quality Reinforcement
### Added
- `settings_gatekeep.py`: Domain normalization & gatekeeping
- New CLI flags: `--log-level`, `--log-json`, `--log-file`
- JSON logging formatter (optional via `LOG_JSON=1`)

### Changed
- All modules: unified logger usage (`logger = logging.getLogger(__name__)`)
- `setup_logging()`: idempotent, supports env override and JSON
- `schedule_writer_if_needed`: improved auto-write logging and env parsing

### Fixed
- Duplicate handler issue on re-init
- Deduplication in `utils.refs.merge_refs`
- Typing in `sanitize_numeric_state_generic`

### Improved
- RAG ref normalization, prompt formatting, backup handling
- Error visibility and structured log clarity
