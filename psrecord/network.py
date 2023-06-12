from subprocess import Popen, PIPE, CalledProcessError
import time
import re
from typing import Optional


def log_network(duration: Optional[int] = None, logfile: str = "network"):

    reg = re.compile(r"\d+\/\d+")

    cmd = "sudo bandwhich -trp".split()

    with open(logfile,  "w") as f:
        f.write(
            "# {0:12s} {1:12s} {2:12s} \n".format(
                "Elapsed time".center(12),
                "Network Up (B)".center(12),
                "Network Down (B)".center(12),
            )
        )

        with Popen(cmd, stdout=PIPE, bufsize=1, universal_newlines=True) as p:
            start_time = time.time()
            for line in p.stdout:
                if "python" in line:
                    for match in reg.findall(line):
                        up, down = map(int, match.split("/"))
                        # print(up, down)
                        f.write(
                            "{0:12.3f} {1:12.3f} {2:12.3f} \n".format(
                                time.time() - start_time, up, down
                            )
                        )
                        # f.flush()
                if duration is not None and time.time() - start_time > duration:
                    p.terminate()
                    break



if __name__ == "__main__":
    log_network(30)
