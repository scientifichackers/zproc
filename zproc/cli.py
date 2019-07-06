import click

import zproc


@click.group()
def cli():
    pass


@click.command("start-server")
@click.argument("server_address", required=False)
@click.option("--pid-file", "-p", type=click.Path())
def start_server(server_address, pid_file):
    proc, addr = zproc.start_server(server_address=server_address)
    print(f"[ZProc] server started @ {addr}")

    if pid_file is not None:
        with open(pid_file, "w") as f:
            f.write(str(proc.pid))
    try:
        proc.join()
    finally:
        if pid_file is not None:
            with open(pid_file, "w") as f:
                f.write("")


cli.add_command(start_server)
