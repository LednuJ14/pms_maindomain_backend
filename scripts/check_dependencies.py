#!/usr/bin/env python3
"""
Dependency checker script
Checks for outdated or vulnerable dependencies
"""
import subprocess
import sys
import json
from pathlib import Path


def check_python_dependencies():
    """Check Python dependencies for security vulnerabilities."""
    print("Checking Python dependencies...")
    
    try:
        # Check for pip-audit (security vulnerability scanner)
        result = subprocess.run(
            ['pip', 'list', '--format=json'],
            capture_output=True,
            text=True,
            check=True
        )
        
        packages = json.loads(result.stdout)
        print(f"Found {len(packages)} installed packages")
        
        # Check for outdated packages
        print("\nChecking for outdated packages...")
        outdated_result = subprocess.run(
            ['pip', 'list', '--outdated', '--format=json'],
            capture_output=True,
            text=True
        )
        
        if outdated_result.returncode == 0:
            outdated = json.loads(outdated_result.stdout)
            if outdated:
                print(f"⚠️  Found {len(outdated)} outdated packages:")
                for pkg in outdated:
                    print(f"  - {pkg['name']}: {pkg['version']} -> {pkg['latest_version']}")
            else:
                print("✅ All packages are up to date")
        else:
            print("⚠️  Could not check for outdated packages")
        
        # Try pip-audit if available
        print("\nChecking for security vulnerabilities...")
        audit_result = subprocess.run(
            ['pip-audit', '--format=json'],
            capture_output=True,
            text=True
        )
        
        if audit_result.returncode == 0:
            vulnerabilities = json.loads(audit_result.stdout)
            if vulnerabilities.get('vulnerabilities'):
                print(f"⚠️  Found {len(vulnerabilities['vulnerabilities'])} vulnerabilities")
                for vuln in vulnerabilities['vulnerabilities']:
                    print(f"  - {vuln.get('name')}: {vuln.get('id')}")
            else:
                print("✅ No known security vulnerabilities")
        else:
            print("ℹ️  pip-audit not installed. Install with: pip install pip-audit")
            print("   Or use: pip check")
            
            # Fallback to pip check
            check_result = subprocess.run(
                ['pip', 'check'],
                capture_output=True,
                text=True
            )
            if check_result.returncode != 0:
                print("⚠️  Dependency conflicts found:")
                print(check_result.stdout)
            else:
                print("✅ No dependency conflicts")
        
    except FileNotFoundError:
        print("❌ pip not found. Please install Python and pip.")
        return False
    except Exception as e:
        print(f"❌ Error checking dependencies: {e}")
        return False
    
    return True


def check_node_dependencies():
    """Check Node.js dependencies for security vulnerabilities."""
    print("\n" + "="*50)
    print("Checking Node.js dependencies...")
    
    frontend_path = Path(__file__).parent.parent.parent / 'frontend'
    
    if not frontend_path.exists():
        print("⚠️  Frontend directory not found")
        return False
    
    try:
        # Check for npm audit
        print("Running npm audit...")
        audit_result = subprocess.run(
            ['npm', 'audit', '--json'],
            cwd=frontend_path,
            capture_output=True,
            text=True
        )
        
        if audit_result.returncode == 0:
            audit_data = json.loads(audit_result.stdout)
            vulnerabilities = audit_data.get('vulnerabilities', {})
            
            if vulnerabilities:
                print(f"⚠️  Found {len(vulnerabilities)} vulnerable packages:")
                for pkg, vuln in list(vulnerabilities.items())[:10]:  # Show first 10
                    severity = vuln.get('severity', 'unknown')
                    print(f"  - {pkg}: {severity}")
                if len(vulnerabilities) > 10:
                    print(f"  ... and {len(vulnerabilities) - 10} more")
            else:
                print("✅ No known security vulnerabilities")
        else:
            print("⚠️  npm audit failed")
        
        # Check for outdated packages
        print("\nChecking for outdated packages...")
        outdated_result = subprocess.run(
            ['npm', 'outdated', '--json'],
            cwd=frontend_path,
            capture_output=True,
            text=True
        )
        
        if outdated_result.returncode == 0:
            outdated = json.loads(outdated_result.stdout)
            if outdated:
                print(f"⚠️  Found {len(outdated)} outdated packages:")
                for pkg, info in list(outdated.items())[:10]:  # Show first 10
                    current = info.get('current', '?')
                    wanted = info.get('wanted', '?')
                    latest = info.get('latest', '?')
                    print(f"  - {pkg}: {current} -> {wanted} (latest: {latest})")
                if len(outdated) > 10:
                    print(f"  ... and {len(outdated) - 10} more")
            else:
                print("✅ All packages are up to date")
        else:
            print("ℹ️  No outdated packages or npm outdated not available")
        
    except FileNotFoundError:
        print("❌ npm not found. Please install Node.js and npm.")
        return False
    except Exception as e:
        print(f"❌ Error checking dependencies: {e}")
        return False
    
    return True


def main():
    """Main function."""
    print("="*50)
    print("Dependency Security Check")
    print("="*50)
    
    python_ok = check_python_dependencies()
    node_ok = check_node_dependencies()
    
    print("\n" + "="*50)
    if python_ok and node_ok:
        print("✅ Dependency check completed")
        sys.exit(0)
    else:
        print("⚠️  Some checks failed")
        sys.exit(1)


if __name__ == '__main__':
    main()

