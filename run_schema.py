# Quick script to run the database schema
import sys
sys.path.insert(0, '/home/scadreau/surgicase')

from core.database import get_db_connection, close_db_connection

# Read SQL file
with open('database_phi_encryption_schema.sql', 'r') as f:
    sql_content = f.read()

# Connect
conn = get_db_connection()
cursor = conn.cursor()

# Remove comments and split into statement blocks
lines = []
for line in sql_content.split('\n'):
    if not line.strip().startswith('--'):
        lines.append(line)

sql = '\n'.join(lines)

# Find statement blocks (things between semicolons that might span multiple lines)
current_statement = []
in_statement = False

for line in sql.split('\n'):
    line = line.strip()
    if not line:
        continue
    
    current_statement.append(line)
    
    if ';' in line:
        # End of statement
        full_statement = ' '.join(current_statement)
        if full_statement and full_statement != ';':
            try:
                cursor.execute(full_statement)
                print(f'✓ OK: {full_statement[:60]}...')
            except Exception as e:
                # Ignore "column already exists" errors
                if 'Duplicate column' in str(e) or 'already exists' in str(e):
                    print(f'⚠ Skipped (already exists): {full_statement[:60]}...')
                else:
                    print(f'✗ Error: {e}')
                    print(f'   SQL: {full_statement[:150]}...')
        current_statement = []

conn.commit()
cursor.close()
close_db_connection(conn)
print('\n✓ Schema execution complete!')

