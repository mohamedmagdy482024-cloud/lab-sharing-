#!/bin/bash

echo "=============================="
echo "  Lab Sharing - Installer"
echo "=============================="

# Check python3
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found. Install it first: sudo apt install python3"
    exit 1
fi

echo "✅ Python3 found: $(python3 --version)"

# Create venv
echo "📦 Creating virtual environment..."
rm -rf venv
python3 -m venv venv

# Install dependencies
echo "📥 Installing dependencies..."
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q

echo ""
echo "✅ Installation complete!"
echo ""
echo "▶️  To run the app:"
echo "    ./run.sh"
echo ""

# Create run script
cat > run.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
./venv/bin/python main.py
EOF

chmod +x run.sh
echo "✅ run.sh created"
