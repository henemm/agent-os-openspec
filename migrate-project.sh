#!/bin/bash

# Agent OS + OpenSpec Migration Script
# Usage: ./migrate-project.sh /path/to/project "ProjectName"

set -e

TEMPLATE_DIR="$HOME/.agent-os-templates"
TARGET_DIR="$1"
PROJECT_NAME="$2"

if [ -z "$TARGET_DIR" ] || [ -z "$PROJECT_NAME" ]; then
    echo "Usage: ./migrate-project.sh /path/to/project \"ProjectName\""
    exit 1
fi

echo "🚀 Migrating $PROJECT_NAME to Agent OS + OpenSpec..."
echo "   Target: $TARGET_DIR"
echo ""

# Create directory structure
echo "📁 Creating directory structure..."
mkdir -p "$TARGET_DIR/.agent-os/standards/global"
mkdir -p "$TARGET_DIR/.agent-os/standards/swiftui"
mkdir -p "$TARGET_DIR/.agent-os/agents"
mkdir -p "$TARGET_DIR/.agent-os/workflows"
mkdir -p "$TARGET_DIR/.claude/commands"
mkdir -p "$TARGET_DIR/openspec/specs/features"
mkdir -p "$TARGET_DIR/openspec/specs/integrations"
mkdir -p "$TARGET_DIR/openspec/changes"
mkdir -p "$TARGET_DIR/DOCS"

# Copy standards (1:1, no changes needed)
echo "📋 Copying standards..."
cp "$TEMPLATE_DIR/standards/global/"*.md "$TARGET_DIR/.agent-os/standards/global/"
cp "$TEMPLATE_DIR/standards/swiftui/"*.md "$TARGET_DIR/.agent-os/standards/swiftui/"

# Copy workflows (generic, placeholders remain)
echo "🔄 Copying workflows..."
cp "$TEMPLATE_DIR/workflows/"*.md "$TARGET_DIR/.agent-os/workflows/"

# Copy agents (need to replace {{PROJECT_NAME}})
echo "🤖 Copying agents..."
for file in "$TEMPLATE_DIR/agents/"*.md; do
    filename=$(basename "$file")
    sed "s/{{PROJECT_NAME}}/$PROJECT_NAME/g" "$file" > "$TARGET_DIR/.agent-os/agents/$filename"
done

# Copy slash commands
echo "⚡ Copying slash commands..."
cp "$TEMPLATE_DIR/slash-commands/"*.md "$TARGET_DIR/.claude/commands/"

# Copy docs templates
echo "📝 Copying docs templates..."
cp "$TEMPLATE_DIR/docs-templates/"*.md "$TARGET_DIR/DOCS/"

# Copy Claude settings
echo "⚙️  Copying Claude settings..."
cp "$TEMPLATE_DIR/claude-config/settings.local.json" "$TARGET_DIR/.claude/"

# Copy OpenSpec project template
echo "📦 Copying OpenSpec project template..."
sed "s/{{PROJECT_NAME}}/$PROJECT_NAME/g" "$TEMPLATE_DIR/claude-config/openspec-project.md.template" > "$TARGET_DIR/openspec/project.md"

# Create CLAUDE.md with placeholders
echo "📄 Creating CLAUDE.md template..."
sed "s/{{PROJECT_NAME}}/$PROJECT_NAME/g" "$TEMPLATE_DIR/CLAUDE.md.template" > "$TARGET_DIR/CLAUDE.md"

echo ""
echo "✅ Migration complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Edit CLAUDE.md - Fill in the {{PLACEHOLDER}} values"
echo "   2. Edit openspec/project.md - Define your app vision and features"
echo "   3. Edit .agent-os/workflows/*.md - Update {{PROJECT_FILE}} and {{SCHEME}} placeholders"
echo "   4. Create feature specs in openspec/specs/features/"
echo "   5. Add project-specific standards to .agent-os/standards/ if needed"
echo ""
echo "📂 Template structure created:"
find "$TARGET_DIR/.agent-os" "$TARGET_DIR/.claude" "$TARGET_DIR/openspec" "$TARGET_DIR/DOCS" -type f 2>/dev/null | head -20
echo "   ..."
