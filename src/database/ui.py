from typing import Dict, Any, List as ListType
import click

def select_database_type() -> str:
    """Interactive menu for database type selection."""
    try:
        from inquirer import prompt, List
        
        choices = [
            'PostgreSQL',
            'MySQL',
            'MariaDB',
            'Oracle Database',
            'Microsoft SQL Server',
            'SQLite',
            'Amazon Aurora',
            'Snowflake'
        ]
        
        questions = [
            List('database',
                 message="Select your database type:",
                 choices=choices)
        ]
        answers = prompt(questions)
        if answers and 'database' in answers:
            return answers['database']
        return choices[0]
    except ImportError:
        click.echo("\n⚠️  Warning: inquirer not installed. Falling back to simple selection.")
        choices = [
            'PostgreSQL', 'MySQL', 'MariaDB', 'Oracle Database',
            'Microsoft SQL Server', 'SQLite', 'Amazon Aurora', 'Snowflake'
        ]
        for i, choice in enumerate(choices, 1):
            click.echo(f"{i}. {choice}")
        
        idx = click.prompt("\nEnter choice (1-8)", type=int, default=1)
        if 1 <= idx <= 8:
            return choices[idx-1]
        return choices[0]

def collect_credentials(db_type: str) -> Dict[str, Any]:
    """Collect database credentials one by one."""
    click.echo(f"\n--- Configuring {db_type} Connection ---")
    credentials = {}
    
    if db_type == 'SQLite':
        credentials['database_path'] = click.prompt('SQLite Database File Path').strip()
    
    elif db_type == 'Snowflake':
        credentials['account'] = click.prompt('Snowflake Account (e.g., xy12345.us-east-1)').strip()
        credentials['username'] = click.prompt('Username').strip()
        credentials['password'] = click.prompt('Password', hide_input=True).strip()
        credentials['database'] = click.prompt('Database').strip()
        credentials['schema'] = click.prompt('Schema', default='PUBLIC').strip()
        credentials['warehouse'] = click.prompt('Warehouse').strip()
        credentials['role'] = click.prompt('Role', default='', show_default=False).strip()
        
    elif db_type == 'Amazon Aurora':
        engine = click.prompt('Aurora Engine Type', type=click.Choice(['mysql', 'postgresql'], case_sensitive=False), default='mysql')
        credentials['engine_type'] = engine
        credentials['host'] = click.prompt('Cluster Endpoint').strip()
        default_port = 3306 if engine == 'mysql' else 5432
        credentials['port'] = click.prompt('Port', default=default_port, type=int)
        credentials['database'] = click.prompt('Database Name').strip()
        credentials['username'] = click.prompt('Username').strip()
        credentials['password'] = click.prompt('Password', hide_input=True).strip()

    elif db_type == 'Oracle Database':
        credentials['host'] = click.prompt('Host', default='localhost').strip()
        credentials['port'] = click.prompt('Port', default=1521, type=int)
        
        oracle_type = click.prompt('Connect via', type=click.Choice(['Service Name', 'SID'], case_sensitive=False), default='Service Name')
        if oracle_type.lower() == 'service name':
            credentials['service_name'] = click.prompt('Service Name').strip()
        else:
            credentials['sid'] = click.prompt('SID').strip()
            
        credentials['username'] = click.prompt('Username').strip()
        credentials['password'] = click.prompt('Password', hide_input=True).strip()

    else:
        # Standard SQL databases (PostgreSQL, MySQL, MariaDB, MSSQL)
        credentials['host'] = click.prompt('Host', default='localhost').strip()
        
        default_ports = {
            'PostgreSQL': 5432,
            'MySQL': 3306,
            'MariaDB': 3306,
            'Microsoft SQL Server': 1433
        }
        credentials['port'] = click.prompt('Port', default=default_ports.get(db_type, 3306), type=int)
        credentials['database'] = click.prompt('Database Name').strip()
        credentials['username'] = click.prompt('Username').strip()
        credentials['password'] = click.prompt('Password', hide_input=True).strip()
        
    return credentials

def display_connection_result(success: bool, message: str):
    """Display the result of a connection test."""
    if success:
        click.echo(f"\n✅ {message}")
    else:
        click.echo(f"\n❌ {message}")
