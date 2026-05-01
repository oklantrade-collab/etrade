
import sys

def check_braces(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    balance = 0
    for i, char in enumerate(content):
        if char == '{':
            balance += 1
        elif char == '}':
            balance -= 1
        
        if balance < 0:
            # Find line number
            line = content.count('\n', 0, i) + 1
            print(f"Error: Negative balance at line {line}")
            # Show context
            start = max(0, i - 50)
            end = min(len(content), i + 50)
            print(f"Context: ...{content[start:end]}...")
            return
    
    print(f"Final balance: {balance}")

if __name__ == "__main__":
    check_braces(sys.argv[1])
