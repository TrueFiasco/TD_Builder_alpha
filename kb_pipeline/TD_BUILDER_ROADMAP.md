# TouchDesigner File Builder - Implementation Roadmap

**Checklist for building a complete, validated TD file generation system**

---

## Phase 1: Research & Analysis ⏱️ 1-2 weeks

### File Format Research
- [ ] Extract 10+ palette .tox files
- [ ] Analyze .toc file format (binary vs. text)
- [ ] Document header/metadata structure
- [ ] Identify operator definition format
- [ ] Identify parameter storage format
- [ ] Identify connection representation
- [ ] Document hierarchy structure
- [ ] Analyze version compatibility markers

### Pattern Discovery
- [ ] Extract all operator types from palette (target: 100+)
- [ ] Map parameter types to storage formats
- [ ] Document connection type patterns
- [ ] Identify naming conventions
- [ ] Document position/layout patterns
- [ ] Find resource reference patterns

### Cross-Reference with Knowledge Base
- [ ] Compare palette operators with KB (673 operators)
- [ ] Validate parameter schemas match
- [ ] Check for undocumented operators
- [ ] Verify operator families (TOP, CHOP, SOP, etc.)
- [ ] Map real examples to patterns

### Deliverables
- [ ] **Format Specification Document** (Markdown)
- [ ] **Operator Type Catalog** (JSON)
- [ ] **Pattern Database** (JSON)
- [ ] **Research Summary Report** (Markdown)

---

## Phase 2: Schema Definition ⏱️ 1 week

### JSON Schema Creation
- [ ] Define base schema structure
- [ ] Define operator schema
  - [ ] Operator type
  - [ ] Name/ID
  - [ ] Position
  - [ ] Parent reference
  - [ ] Parameters
- [ ] Define parameter schema
  - [ ] Type system (int, float, str, menu, etc.)
  - [ ] Value constraints
  - [ ] Expression mode
  - [ ] Default values
- [ ] Define connection schema
  - [ ] Source/target references
  - [ ] Input/output indices
  - [ ] Wire type
- [ ] Define network schema
  - [ ] Hierarchy
  - [ ] Layout
  - [ ] Viewer state
- [ ] Define metadata schema
  - [ ] Version
  - [ ] Build number
  - [ ] Author/timestamp

### Validation Rules
- [ ] Document all naming rules
- [ ] Document all hierarchy rules
- [ ] Document all connection rules
- [ ] Document all parameter rules
- [ ] Document version compatibility rules
- [ ] Categorize rules (error vs. warning)
- [ ] Create rule database with examples

### Deliverables
- [ ] **JSON Schema file** (`td_project_schema.json`)
- [ ] **Validation Rules Database** (`validation_rules.json`)
- [ ] **Type System Documentation** (Markdown)

---

## Phase 3: Parser Implementation ⏱️ 1-2 weeks

### .toc Parser
- [ ] Implement binary/text format detection
- [ ] Implement .toc file parser
- [ ] Extract operator definitions
- [ ] Extract parameters
- [ ] Extract connections
- [ ] Extract metadata
- [ ] Handle nested structures (.dir/)

### JSON Converter
- [ ] Convert .toc to standardized JSON
- [ ] Normalize operator types
- [ ] Normalize parameter values
- [ ] Normalize connection references
- [ ] Preserve all metadata

### Testing
- [ ] Test with 10+ palette components
- [ ] Validate against JSON schema
- [ ] Handle edge cases (empty files, complex nesting)
- [ ] Performance benchmarks

### Deliverables
- [ ] **TocParser class** (`toc_parser.py`)
- [ ] **JSON converter** (`toc_to_json.py`)
- [ ] **Parser test suite** (`test_parser.py`)

---

## Phase 4: Validation System ⏱️ 1-2 weeks

### Stage 1: Schema Validation
- [ ] JSON schema validator
- [ ] Type checking
- [ ] Required field validation
- [ ] Format validation

### Stage 2: Semantic Validation
- [ ] Operator type validation (against registry)
- [ ] Parameter validation (against operator schema)
- [ ] Parameter value validation (type, range, menu)
- [ ] Family validation (TOP, CHOP, etc.)

### Stage 3: Reference Validation
- [ ] Operator path resolution
- [ ] Parent existence checks
- [ ] Connection endpoint validation
- [ ] No dangling references

### Stage 4: Logical Validation
- [ ] No circular parent-child
- [ ] Connection type compatibility (TOP→TOP, etc.)
- [ ] No duplicate names in scope
- [ ] Valid hierarchy depth

### Stage 5: TD-Specific Validation
- [ ] Version compatibility
- [ ] Build number checks
- [ ] Operator availability by version
- [ ] Deprecated features

### Error Reporting
- [ ] ValidationResult dataclass
- [ ] ValidationError with location/suggestion
- [ ] ValidationWarning for non-fatal issues
- [ ] Human-readable error messages

### Deliverables
- [ ] **Validator class** (`td_validator.py`)
- [ ] **Validation stages** (5 modules)
- [ ] **Error reporting system** (`validation_result.py`)
- [ ] **Validation test suite** (`test_validator.py`)

---

## Phase 5: Operator Registry ⏱️ 1 week

### Registry Construction
- [ ] Load operator data from KB (673 operators)
- [ ] Parse parameter schemas
- [ ] Identify operator families
- [ ] Mark COMP types
- [ ] Extract version requirements
- [ ] Build operator type index

### Registry API
- [ ] `get_operator_schema(op_type)` - Get full schema
- [ ] `validate_parameter(op_type, param, value)` - Validate param
- [ ] `get_default_parameters(op_type)` - Get defaults
- [ ] `is_comp(op_type)` - Check if COMP
- [ ] `get_family(op_type)` - Get family (TOP/CHOP/etc.)
- [ ] `is_valid_connection(src_type, tgt_type)` - Check compatibility

### Testing
- [ ] Verify all 673 operators loaded
- [ ] Test parameter validation for each type
- [ ] Test connection compatibility matrix
- [ ] Performance benchmarks (must be fast)

### Deliverables
- [ ] **OperatorRegistry class** (`operator_registry.py`)
- [ ] **Operator metadata JSON** (`operator_metadata.json`)
- [ ] **Registry test suite** (`test_registry.py`)

---

## Phase 6: Builder Implementation ⏱️ 2 weeks

### Core Builder
- [ ] TDProjectBuilder class initialization
- [ ] Internal data structures (operators, connections)
- [ ] State management

### Operator Management
- [ ] `add_operator()` method
- [ ] Name uniqueness checking
- [ ] Parent validation
- [ ] Position management
- [ ] Parameter setting with validation

### Connection Management
- [ ] `connect()` method
- [ ] Source/target validation
- [ ] Index validation
- [ ] Type compatibility checking
- [ ] Multi-input handling

### Validation Integration
- [ ] `validate()` method
- [ ] Run all validation stages
- [ ] Collect errors/warnings
- [ ] Return ValidationResult

### File Generation
- [ ] `build()` method
- [ ] Generate .toc structure
- [ ] Create .dir/ hierarchy
- [ ] Package as ZIP
- [ ] Write to disk

### Advanced Features
- [ ] `from_json()` - Load from JSON
- [ ] `to_json()` - Export to JSON
- [ ] `clone_operator()` - Duplicate operator
- [ ] `remove_operator()` - Delete operator
- [ ] `import_tox()` - Import existing .tox

### Deliverables
- [ ] **TDProjectBuilder class** (`td_builder.py`)
- [ ] **Builder test suite** (`test_builder.py`)
- [ ] **Usage examples** (`examples/`)

---

## Phase 7: Testing & Validation ⏱️ 1-2 weeks

### Unit Tests
- [ ] Test all validation rules individually
- [ ] Test operator registry methods
- [ ] Test builder methods
- [ ] Test parser methods
- [ ] Target: >95% code coverage

### Integration Tests
- [ ] Parse + validate roundtrip
- [ ] Build + validate generated files
- [ ] Test with palette components
- [ ] Test with synthetic examples

### Real-World Validation
- [ ] Test with all 121 palette components
- [ ] Load in actual TouchDesigner
- [ ] Verify no loading errors
- [ ] Verify functionality preserved

### Edge Case Testing
- [ ] Empty project
- [ ] Maximum complexity (1000+ operators)
- [ ] Deep nesting (10+ levels)
- [ ] Complex connections (feedback loops)
- [ ] All operator types

### Performance Testing
- [ ] Validation speed (<100ms for typical)
- [ ] Build speed (<1s for typical)
- [ ] Memory usage
- [ ] Scaling (large projects)

### Deliverables
- [ ] **Complete test suite** (`tests/`)
- [ ] **Test coverage report**
- [ ] **Performance benchmarks**
- [ ] **Real-world validation report**

---

## Phase 8: Documentation ⏱️ 1 week

### API Documentation
- [ ] TDProjectBuilder API reference
- [ ] Validator API reference
- [ ] OperatorRegistry API reference
- [ ] Parser API reference

### User Guide
- [ ] Quick start guide
- [ ] Basic usage examples
- [ ] Advanced usage examples
- [ ] Error handling guide

### Developer Guide
- [ ] Architecture overview
- [ ] Extending the builder
- [ ] Adding new operator types
- [ ] Custom validation rules

### Reference Documentation
- [ ] File format specification
- [ ] Validation rules reference
- [ ] Operator type catalog
- [ ] Parameter type reference

### Deliverables
- [ ] **API Documentation** (Sphinx/MkDocs)
- [ ] **User Guide** (Markdown)
- [ ] **Developer Guide** (Markdown)
- [ ] **Reference Docs** (Markdown)

---

## Phase 9: Integration ⏱️ 1 week

### MCP Server Integration
- [ ] Add `generate_project` tool to MCP server
- [ ] Integrate with orchestrator system
- [ ] Add validation endpoint
- [ ] Add template system

### Orchestrator Integration
- [ ] AI can call builder via MCP
- [ ] Validate before presenting to user
- [ ] Error handling in orchestrator
- [ ] Cost tracking for generation

### Template System
- [ ] Create common project templates
- [ ] Audio visualization template
- [ ] Particle system template
- [ ] Data visualization template
- [ ] Generic templates for each operator family

### Deliverables
- [ ] **Updated MCP server** (`server_with_agents.py`)
- [ ] **Template library** (`templates/`)
- [ ] **Integration tests**

---

## Phase 10: Production Hardening ⏱️ 1 week

### Error Handling
- [ ] Graceful failures
- [ ] User-friendly error messages
- [ ] Logging system
- [ ] Debug mode

### Performance Optimization
- [ ] Profile validation
- [ ] Optimize hot paths
- [ ] Cache operator schemas
- [ ] Lazy loading where possible

### Security
- [ ] Sanitize user input
- [ ] Validate file paths
- [ ] Prevent ZIP bombs
- [ ] Resource limits

### Monitoring
- [ ] Usage metrics
- [ ] Error tracking
- [ ] Performance metrics
- [ ] Validation failure patterns

### Deliverables
- [ ] **Production-ready code**
- [ ] **Logging system**
- [ ] **Monitoring dashboard**
- [ ] **Performance report**

---

## Success Criteria Checklist

### Functionality
- [ ] Can parse all 121 palette .tox files
- [ ] Can generate valid .tox files for all 673 operator types
- [ ] All generated files load in TouchDesigner without errors
- [ ] Validation catches all known error patterns
- [ ] No false positives in validation

### Performance
- [ ] Validation: <100ms for typical projects
- [ ] Building: <1s for typical projects
- [ ] Parsing: <500ms for typical .tox files
- [ ] Memory: <100MB for typical projects

### Quality
- [ ] Test coverage: >95%
- [ ] All validation rules documented
- [ ] All operator types supported
- [ ] Complete API documentation
- [ ] User guide with examples

### Integration
- [ ] MCP server integration complete
- [ ] Orchestrator can generate projects
- [ ] Template system working
- [ ] Error handling robust

---

## Risk Mitigation

### Known Risks

**Risk 1: Format Undocumented**
- Mitigation: Extensive reverse engineering, multiple example analysis
- Fallback: Community resources, TouchDesigner forums

**Risk 2: Format Changes Across Versions**
- Mitigation: Support multiple versions, version detection
- Fallback: Focus on latest stable version first

**Risk 3: Complex Edge Cases**
- Mitigation: Extensive testing with real files
- Fallback: Document unsupported features, provide workarounds

**Risk 4: Performance Issues**
- Mitigation: Profile early, optimize hot paths
- Fallback: Async processing for large projects

**Risk 5: Incomplete Operator Coverage**
- Mitigation: Use knowledge base (673 operators)
- Fallback: Graceful degradation for unknown operators

---

## Timeline Summary

| Phase | Duration | Dependencies | Deliverables |
|-------|----------|--------------|-------------|
| 1. Research | 1-2 weeks | None | Format spec, patterns |
| 2. Schema | 1 week | Phase 1 | JSON schema, rules |
| 3. Parser | 1-2 weeks | Phase 2 | Parser, converter |
| 4. Validator | 1-2 weeks | Phase 2, 3 | Validation system |
| 5. Registry | 1 week | Knowledge base | Operator registry |
| 6. Builder | 2 weeks | Phase 4, 5 | Builder API |
| 7. Testing | 1-2 weeks | Phase 6 | Test suite |
| 8. Documentation | 1 week | All phases | Docs |
| 9. Integration | 1 week | Phase 6, MCP | MCP integration |
| 10. Hardening | 1 week | Phase 9 | Production ready |

**Total: 10-13 weeks** (aggressive timeline with full-time focus)

**Realistic: 3-4 months** (with other responsibilities)

---

## Resource Requirements

### Development
- Python 3.10+
- TouchDesigner 2023+ (for testing)
- ZIP library (built-in)
- JSON Schema validator
- pytest (testing)

### Knowledge Base Access
- KB pipeline: `C:\TD_Projects\kb_pipeline\`
- Palette files
- Operator documentation
- Knowledge graph

### Tools
- Code editor (VS Code)
- TouchDesigner (for validation)
- ZIP extractor
- JSON viewer

---

## Next Steps

1. **Review roadmap** with team/stakeholders
2. **Start Phase 1** - Extract first 10 palette .tox files
3. **Set up project structure** - Create directories
4. **Initialize git repo** - Version control
5. **Create progress tracker** - Track checklist items

**Ready to begin!** Copy the planning prompt into ChatGPT to get architectural guidance.
