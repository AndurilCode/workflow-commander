# Configuration Service Migration Strategy

## Overview

This document outlines the systematic migration strategy for extracting configuration management from scattered global variables and files into a centralized configuration service.

## Current State Analysis

### Configuration Sources Identified
1. **ServerConfig** (`src/dev_workflow_mcp/config.py`)
   - CLI argument parsing and server configuration
   - Repository path, session management, cache settings
   - Directory creation and validation methods

2. **WorkflowConfig** (`src/dev_workflow_mcp/models/config.py`)
   - CLI-driven workflow behavior configuration
   - Local state file settings and format options

3. **S3Config** (`src/dev_workflow_mcp/models/config.py`)
   - Environment variable-based configuration
   - AWS S3 integration settings

4. **Global State** (`src/dev_workflow_mcp/utils/session_manager.py`)
   - `_server_config` global variable with threading locks
   - Cache manager initialization dependencies

### Configuration Dependencies
- **server.py**: Creates ServerConfig from CLI args, passes to prompt registration
- **session_manager.py**: Stores global _server_config, manages cache initialization
- **prompts/*.py**: Receive config via function parameters
- **config_utils.py**: Factory functions for WorkflowConfig creation

## Migration Phases

### Phase 1: Service Foundation Implementation ✅
- [x] Create service interface and protocols
- [x] Implement configuration data models
- [x] Create dependency injection framework
- [x] Design backward compatibility layer

### Phase 2: Server Configuration Migration
**Target**: Migrate server.py to use new configuration service

**Steps**:
1. Update `server.py` to create ServerConfiguration from CLI args
2. Initialize ConfigurationService in main() function
3. Register configuration service in dependency injection container
4. Update prompt registration to use injected configuration service
5. Add integration tests for server startup

**Files Modified**:
- `src/dev_workflow_mcp/server.py`
- `src/dev_workflow_mcp/prompts/phase_prompts.py`
- `src/dev_workflow_mcp/prompts/discovery_prompts.py`

### Phase 3: Session Manager Migration
**Target**: Remove global _server_config variable from session_manager.py

**Steps**:
1. Replace `set_server_config()` with dependency injection
2. Update cache manager initialization to use configuration service
3. Remove global _server_config variable and threading locks
4. Update all functions to get configuration from service
5. Add session manager integration tests

**Files Modified**:
- `src/dev_workflow_mcp/utils/session_manager.py`
- `src/dev_workflow_mcp/utils/cache_manager.py`

### Phase 4: Workflow Configuration Migration
**Target**: Migrate WorkflowConfig and config utilities

**Steps**:
1. Update `config_utils.py` to use configuration service
2. Remove `WorkflowConfig.from_server_config()` factory method
3. Update workflow loading to use configuration service
4. Migrate workflow validation settings
5. Add workflow configuration tests

**Files Modified**:
- `src/dev_workflow_mcp/utils/config_utils.py`
- `src/dev_workflow_mcp/models/config.py`
- Workflow loading components

### Phase 5: Platform Configuration Migration
**Target**: Migrate CLI and platform-specific settings

**Steps**:
1. Extract platform configuration from CLI handlers
2. Consolidate environment variable handling
3. Update CLI commands to use configuration service
4. Add platform configuration validation
5. Test CLI functionality with new configuration

**Files Modified**:
- `src/workflow_commander_cli/main.py`
- `src/workflow_commander_cli/handlers/*.py`
- Platform-specific configuration files

### Phase 6: Legacy Cleanup
**Target**: Remove old configuration code and ensure clean architecture

**Steps**:
1. Remove old ServerConfig class (after full migration)
2. Clean up scattered configuration loading code
3. Remove duplicate validation logic
4. Update imports and documentation
5. Final integration testing

**Files Modified**:
- `src/dev_workflow_mcp/config.py` (potential removal)
- Various files with configuration imports
- Documentation updates

## Backward Compatibility Strategy

### During Migration
- Keep existing ServerConfig class operational
- Provide `to_legacy_server_config()` method for compatibility
- Maintain existing function signatures where possible
- Use feature flags to enable new configuration service gradually

### Post-Migration
- Deprecation warnings for old configuration methods
- Documentation updates with migration examples
- Version bump to indicate breaking changes
- Support old configuration for 1-2 major versions

## Validation Strategy

### Unit Tests
- Test each configuration model independently
- Test dependency injection container functionality
- Test configuration service initialization and validation
- Test backward compatibility conversion methods

### Integration Tests
- Test server startup with new configuration service
- Test workflow execution with migrated configuration
- Test CLI functionality with platform configuration
- Test cache manager with injected configuration

### Migration Tests
- Test gradual migration scenarios
- Test rollback procedures
- Test configuration validation during migration
- Test error handling for invalid configurations

## Risk Mitigation

### High-Risk Areas
1. **Global State Management**: _server_config variable removal
2. **Threading**: Configuration access in multi-threaded environment
3. **Cache Initialization**: Complex dependency on server configuration
4. **CLI Integration**: Platform-specific configuration handling

### Mitigation Strategies
1. **Phased Migration**: Implement changes incrementally with validation
2. **Feature Flags**: Enable new configuration service gradually
3. **Rollback Plan**: Maintain old configuration system during migration
4. **Comprehensive Testing**: Unit, integration, and migration-specific tests
5. **Documentation**: Clear migration guides and examples

## Success Metrics

### Code Quality Metrics
- Reduction in global variables (target: eliminate _server_config)
- Reduction in configuration-related coupling
- Improved test coverage for configuration components
- Elimination of duplicate configuration validation

### Performance Metrics
- No degradation in server startup time
- Maintained or improved configuration loading performance
- Reduced memory usage from eliminated duplicate configuration storage

### Maintainability Metrics
- Simplified configuration modification process
- Clear separation of configuration concerns
- Improved configuration documentation and examples
- Easier addition of new configuration options

## Implementation Timeline

**Week 1**: Service Foundation (Phase 1) ✅
**Week 2**: Server Configuration Migration (Phase 2)
**Week 3**: Session Manager Migration (Phase 3)
**Week 4**: Workflow & Platform Migration (Phases 4-5)
**Week 5**: Legacy Cleanup & Testing (Phase 6)

## Next Steps

1. **Phase 2 Implementation**: Begin server configuration migration
2. **Test Development**: Create comprehensive test suite for migration
3. **Documentation**: Create developer migration guide
4. **Validation**: Set up continuous integration for migration testing 