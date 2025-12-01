# ALFRD Prompt Configurations

This directory contains YAML configuration files for all prompts used in the ALFRD system. These prompts are loaded into the PostgreSQL database during initialization and serve as the starting point for the self-improving prompt system.

## Structure

```
prompts/
├── classifier.yaml           # Document classification prompt
├── document_types.yaml       # Known document types
├── summarizers/              # Type-specific summarization prompts
│   ├── bill.yaml
│   ├── finance.yaml
│   ├── school.yaml
│   ├── event.yaml
│   ├── advertising.yaml
│   ├── junk.yaml
│   └── generic.yaml
└── README.md
```

## File Format

### Classifier Prompt (classifier.yaml)

```yaml
version: 1                    # Prompt version number
prompt_type: classifier       # Must be "classifier"
document_type: null           # Always null for classifier
max_words: 300                # Maximum words for this prompt

prompt_text: |
  [The actual prompt text used by the LLM]

output_schema:
  type: object
  required: [...]
  properties: ...             # JSON Schema for expected output

performance_metrics:
  min_confidence: 0.7
  high_confidence_threshold: 0.8
  scoring_threshold: 0.05
```

### Summarizer Prompts (summarizers/*.yaml)

```yaml
version: 1                    # Prompt version number
prompt_type: summarizer       # Must be "summarizer"
document_type: bill           # Specific document type

prompt_text: |
  [The actual prompt text used by the LLM]

output_schema:
  type: object
  properties: ...             # JSON Schema for expected output
```

### Document Types (document_types.yaml)

```yaml
document_types:
  - type_name: bill
    description: Utility bills, service invoices, recurring charges
    is_active: true
    usage_count: 0
```

## How It Works

1. **Initialization**: When you run `./scripts/init-db`, the YAML files are read and loaded into the PostgreSQL `prompts` and `document_types` tables.

2. **Self-Improvement**: Once loaded, the prompts evolve automatically:
   - **Classifier Prompt**: Improved based on classification accuracy
   - **Summarizer Prompts**: Improved based on extraction quality (per document type)

3. **Versioning**: Each improvement creates a new version in the database. The YAML files represent version 1 (the starting point).

## Modifying Prompts

### Option 1: Edit YAML Files (Recommended for Initial Setup)

1. Edit the YAML file with your changes
2. Run `./scripts/init-db` to reinitialize the database (⚠️ DELETES ALL DATA)
3. The system will use your updated prompts as version 1

### Option 2: Let the System Evolve (Recommended for Production)

1. Load the initial prompts from YAML
2. Let the scorer workers automatically improve them over time
3. View evolution with `./scripts/view-prompts`

## Output Schemas

Each prompt includes a JSON Schema defining the expected output structure. This:
- Documents what the LLM should return
- Can be used for validation (future enhancement)
- Helps the LLM understand the desired output format
- Provides typing information for developers

## Adding New Document Types

To add a new document type:

1. **Add to document_types.yaml**:
   ```yaml
   - type_name: receipt
     description: Purchase receipts, transaction records
     is_active: true
     usage_count: 0
   ```

2. **Create summarizer YAML**:
   Create `prompts/summarizers/receipt.yaml` with appropriate fields

3. **Reinitialize database**:
   ```bash
   ./scripts/init-db
   ```

## Performance Tuning

The `performance_metrics` section in classifier.yaml can be adjusted:

- `min_confidence`: Minimum acceptable confidence score
- `high_confidence_threshold`: What counts as "high confidence"
- `scoring_threshold`: Minimum score improvement to create new prompt version

These are also configurable in `shared/config.py` for runtime overrides.

## Best Practices

1. **Keep classifier prompt under 300 words** - It processes every document
2. **Be specific in summarizers** - Each document type has unique fields
3. **Use JSON Schema** - Documents expected output structure
4. **Test before deploying** - Use sample documents to validate changes
5. **Version control** - Track YAML changes in git

## Examples

### Viewing Current Prompts

```bash
# View all prompts and their evolution
./scripts/view-prompts

# View only classifiers
./scripts/view-prompts --type classifier

# View only summarizers
./scripts/view-prompts --type summarizer
```

### Checking Performance

```bash
# View documents with their classifications
./scripts/view-document --stats
```

## Future Enhancements

- [ ] Prompt validation on load (check output_schema validity)
- [ ] Prompt testing framework
- [ ] Export evolved prompts back to YAML
- [ ] A/B testing between prompt versions
- [ ] Prompt performance analytics dashboard