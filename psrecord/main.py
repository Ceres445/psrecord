# Copyright (c) 2013, Thomas P. Robitaille
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from __future__ import unicode_literals, division, print_function, absolute_import
import subprocess

import time
import argparse

children = []


def get_percent(process):
    return process.cpu_percent()


def get_memory(process):
    return process.memory_info()


def get_io(process):
    return process.io_counters()


def all_children(pr):
    global children

    try:
        children_of_pr = pr.children(recursive=True)
    except Exception:  # pragma: no cover
        return children

    for child in children_of_pr:
        if child not in children:
            children.append(child)

    return children


def main():
    parser = argparse.ArgumentParser(
        description="Record CPU and memory usage for a process Extended by Ceres"
    )

    parser.add_argument(
        "process_id_or_command", type=str, help="the process id or command"
    )

    parser.add_argument("--log", type=str, help="output the statistics to a file")

    parser.add_argument("--plot", type=str, help="output the statistics to a plot")

    parser.add_argument(
        "--duration",
        type=float,
        help="how long to record for (in seconds). If not "
        "specified, the recording is continuous until "
        "the job exits.",
    )

    parser.add_argument(
        "--interval",
        type=float,
        help="how long to wait between each sample (in "
        "seconds). By default the process is sampled "
        "as often as possible.",
    )

    parser.add_argument(
        "--include-children",
        help="include sub-processes in statistics (results "
        "in a slower maximum sampling rate).",
        action="store_true",
    )

    args = parser.parse_args()

    # Attach to process
    try:
        pid = int(args.process_id_or_command)
        print("Attaching to process {0}".format(pid))
        sprocess = None
    except Exception:
        import subprocess

        command = args.process_id_or_command
        print("Starting up command '{0}' and attaching to process".format(command))
        sprocess = subprocess.Popen(command, shell=True)
        pid = sprocess.pid

    monitor(
        pid,
        logfile=args.log,
        plot=args.plot,
        duration=args.duration,
        interval=args.interval,
        include_children=args.include_children,
    )

    if sprocess is not None:
        sprocess.kill()


def monitor(
    pid, logfile=None, plot=None, duration=None, interval=None, include_children=False
):
    # We import psutil here so that the module can be imported even if psutil
    # is not present (for example if accessing the version)
    import psutil

    # import scapy

    pr = psutil.Process(pid)

    # Record start time
    start_time = time.time()

    if logfile is None:
        logfile = "psrecord_{0}.log".format(pid)

    if logfile:
        f = open(logfile, "w")
        f.write(
            "# {0:12s} {1:12s} {2:12s} {3:12s} {4:12s} {5:12s}\n".format(
                "Elapsed time".center(12),
                "CPU (%)".center(12),
                "Real (MB)".center(12),
                "Virtual (MB)".center(12),
                "IO Read (MB)".center(12),
                "IO Write (MB)".center(12),
            )
        )

    log = {}
    log["times"] = []
    log["cpu"] = []
    log["mem_real"] = []
    log["mem_virtual"] = []
    log["io_read"] = []
    log["io_write"] = []

    # Start a new thread to log the network data

    from threading import Thread
    from psrecord import log_network

    network_log = logfile.replace(".log", "_network.log")

    t = Thread(target=log_network, args=(duration, network_log))
    t.setDaemon(True)
    t.start()

    try:
        # Start main event loop
        while True:
            # Find current time
            current_time = time.time()

            try:
                pr_status = pr.status()
            except TypeError:  # psutil < 2.0
                pr_status = pr.status
            except psutil.NoSuchProcess:  # pragma: no cover
                break

            # Check if process status indicates we should exit
            if pr_status in [psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD]:
                print(
                    "Process finished ({0:.2f} seconds)".format(
                        current_time - start_time
                    )
                )
                break

            # Check if we have reached the maximum time
            if duration is not None and current_time - start_time > duration:
                break

            # Get current CPU and memory
            try:
                current_cpu = get_percent(pr)
                current_mem = get_memory(pr)
                current_io = get_io(pr)
            except Exception:
                break
            current_mem_real = current_mem.rss / 1024.0**2
            current_mem_virtual = current_mem.vms / 1024.0**2
            current_io_read = current_io.read_bytes
            current_io_write = current_io.write_bytes
            # Get information for children
            if include_children:
                for child in all_children(pr):
                    try:
                        current_cpu += get_percent(child)
                        current_mem = get_memory(child)
                        current_io = get_io(child)
                    except Exception:
                        continue
                    current_mem_real += current_mem.rss / 1024.0**2
                    current_mem_virtual += current_mem.vms / 1024.0**2
                    current_io_read += current_io.read_bytes
                    current_io_write += current_io.write_bytes

            if logfile:
                f.write(
                    "{0:12.3f} {1:12.3f} {2:12.3f} {3:12.3f} {4:12.3f} {5:12.3f}\n".format(
                        current_time - start_time,
                        current_cpu,
                        current_mem_real,
                        current_mem_virtual,
                        current_io_read,
                        current_io_write,
                    )
                )
                f.flush()

            if interval is not None:
                time.sleep(interval)

            # If plotting, record the values
            if plot:
                log["times"].append(current_time - start_time)
                log["cpu"].append(current_cpu)
                log["mem_real"].append(current_mem_real)
                log["mem_virtual"].append(current_mem_virtual)
                log["io_read"].append(current_io_read)
                log["io_write"].append(current_io_write)

    except KeyboardInterrupt:  # pragma: no cover
        pass

    if logfile:
        f.close()

    if plot:
        # Use non-interactive backend, to enable operation on headless machines
        import matplotlib.pyplot as plt

        with plt.rc_context({"backend": "Agg"}):
            # Add three separate plots for cpu, memory, and io

            fig, [[cpu_ax, mem_ax], [io_ax, net_ax]] = plt.subplots(
                2, 2, figsize=(16, 16)
            )
            plt.subplots_adjust(wspace=0.4)

            cpu_ax.plot(log["times"], log["cpu"], "-", lw=1, color="r")

            cpu_ax.set_ylabel("CPU (%)", color="r")
            cpu_ax.set_xlabel("time (s)")
            cpu_ax.set_ylim(0.0, max(log["cpu"]) * 1.2)

            mem_ax.plot(log["times"], log["mem_real"], "-", lw=1, color="b")
            mem_ax.set_ylim(0.0, max(log["mem_real"]) * 1.2)

            mem_ax.set_ylabel("Real Memory (MB)", color="b")
            mem_vir = mem_ax.twinx()
            mem_vir.plot(log["times"], log["mem_virtual"], "-", lw=1, color="g")
            mem_vir.set_ylim(0.0, max(log["mem_virtual"]) * 1.2)
            mem_vir.set_ylabel("Virtual Memory (MB)", color="g")

            # ax.grid()

            io_ax.plot(log["times"], log["io_read"], "-", lw=1, color="b")
            io_ax.set_ylim(0.0, max(log["io_read"]) * 1.2)
            io_ax.set_ylabel("IO Read (MB)", color="b")
            io_wri = io_ax.twinx()
            io_wri.plot(log["times"], log["io_write"], "-", lw=1, color="g")
            io_wri.set_ylim(0.0, max(log["io_write"]) * 1.2)
            io_wri.set_ylabel("IO Write (MB)", color="g")

            with open(network_log, "r") as f:
                network_data = f.readlines()[1:]
            network_data = [line.split() for line in network_data]
            times, upload, download = zip(*network_data)
            times = list(map( lambda x: float(x) - start_time, times))
            upload = list(map(float, upload))
            download = list(map(float, download))
            net_ax.plot(times, upload, "-", lw=1, color="b")
            net_down = net_ax.twinx()
            net_down.plot(times, download, "-", lw=1, color="g")
            net_ax.set_ylabel("Network Upload (MB)", color="b")
            net_ax.set_ylim(0.0, max(upload) * 1.2)
            net_down.set_ylim(0.0, max(download) * 1.2)
            net_down.set_ylabel("Network Download (MB)", color="g")

            fig.savefig(plot)
