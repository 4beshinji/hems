# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "httpx",
#     "rich",
#     "beautifulsoup4",
# ]
# ///

import asyncio
import socket
import ipaddress
import httpx
from bs4 import BeautifulSoup
from rich.console import Console
from rich.table import Table
from rich.progress import Progress

NETWORK = "192.168.128.0/24"
PORTS = [80, 443, 8080, 8081, 8888, 554]
TIMEOUT = 2.0

console = Console(width=200)

async def check_port(ip, port):
    try:
        conn = asyncio.open_connection(str(ip), port)
        reader, writer = await asyncio.wait_for(conn, timeout=TIMEOUT)
        writer.close()
        await writer.wait_closed()
        return (str(ip), port, True)
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        return (str(ip), port, False)
    except Exception:
        return (str(ip), port, False)

async def get_service_info(ip, port):
    if port == 554:
        return "[cyan]RTSP (Likely Camera)[/cyan]"
    
    protocol = "https" if port == 443 else "http"
    url = f"{protocol}://{ip}:{port}"
    
    async with httpx.AsyncClient(verify=False, timeout=2.0, follow_redirects=True) as client:
        try:
            response = await client.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.title.string.strip() if soup.title else "No Title"
            server = response.headers.get("Server", "Unknown")
            return f"[green]HTTP {response.status_code}[/green] - {title} ({server})"
        except httpx.ConnectError:
             return "[red]Connection Error[/red]"
        except httpx.TimeoutException:
             return "[yellow]Timeout[/yellow]"
        except Exception as e:
            return f"[red]Error: {str(e)[:30]}[/red]"

async def scan():
    console.print(f"[bold blue]Scanning network: {NETWORK}[/bold blue]")
    
    net = ipaddress.ip_network(NETWORK)
    hosts = list(net.hosts())
    
    active_services = []

    with Progress() as progress:
        task_scan = progress.add_task("[cyan]Scanning ports...", total=len(hosts))
        
        chunk_size = 50
        for i in range(0, len(hosts), chunk_size):
            chunk = hosts[i:i + chunk_size]
            
            # Create port scan tasks
            scan_tasks = []
            for ip in chunk:
                for port in PORTS:
                    scan_tasks.append(check_port(ip, port))
            
            results = await asyncio.gather(*scan_tasks)
            
            # Process results
            for ip, port, is_open in results:
                if is_open:
                    active_services.append((ip, port))
            
            progress.update(task_scan, advance=len(chunk))

    console.print(f"[bold green]Found {len(active_services)} open ports. Identifying services...[/bold green]")

    table = Table(title="Network Scan Results")
    table.add_column("IP Address", style="cyan")
    table.add_column("Port", style="magenta")
    table.add_column("Service Info", style="white")

    with Progress() as progress:
        task_identify = progress.add_task("[magenta]Identifying services...", total=len(active_services))
        
        info_tasks = []
        for ip, port in active_services:
            info_tasks.append(get_service_info(ip, port))
            
        infos = await asyncio.gather(*info_tasks)
        
        for (ip, port), info in zip(active_services, infos):
            table.add_row(ip, str(port), info)
            progress.update(task_identify, advance=1)

    console.print(table)

if __name__ == "__main__":
    asyncio.run(scan())
