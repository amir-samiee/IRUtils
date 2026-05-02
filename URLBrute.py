from requests.exceptions import ReadTimeout, ConnectionError, ConnectTimeout
from rich_argparse_plus import RichHelpFormatterPlus
from rich.progress import Progress, BarColumn
from typing import Iterable, TypeAlias
from argparse import ArgumentParser
from collections import OrderedDict
from urllib3.util import parse_url
import requests, warnings, logging
from rich import get_console
from pathlib import Path

console = get_console()
logger = logging.getLogger()
FILEDIR = Path(__file__).parent
Result: TypeAlias = requests.Response | BaseException
logging.basicConfig(filename=FILEDIR / ".log", level=0)
expected_exceptions = ConnectionError, ConnectTimeout, ReadTimeout
abbv = {k.__name__: v for k, v in zip(expected_exceptions, ("C.E.", "C.To.", "R.To."))}
parser = ArgumentParser(allow_abbrev=True, formatter_class=RichHelpFormatterPlus)
style_modify = {"argparse.metavar": "yellow", "argparse.prog": "bold green"}
parser.add_argument("--output", default=FILEDIR / "results.txt")
parser.add_argument("--input", default=FILEDIR / "domains.txt")
RichHelpFormatterPlus.styles.update(style_modify)


class Address(str):
    pro = "https://"

    def __new__(cls, value=""):
        if "." not in value:
            msg = "%s doesn't actually seem like a real web address to me" % repr(value)
            warnings.warn(msg)
        return super().__new__(cls, parse_url(value).host)

    @property
    def domain(self):
        return self

    @property
    def url(self):
        return self.pro + self

    def get(self, *args, **kwargs):
        try:
            response = requests.get(self.url, *args, **kwargs)
        except BaseException as err:
            return err
        return response


class Reacheck:
    def __init__(self, addresses: list[str], timeout=5.0):
        # OrderedDicts used as ordered-set-like data structures
        self.addresses = OrderedDict.fromkeys(map(Address, addresses))
        self.reached = OrderedDict()
        self.timeout = timeout
        self.errstats = {}

    def reachout(self):
        self._init_progress()
        with self.progress:
            for i, addr in enumerate(list(self.addresses), 1):
                self.pre_get(i, addr)
                result = addr.get(timeout=self.timeout)
                do_continue = self.post_get(addr, result)
                if do_continue is False:
                    break

    def _init_progress(self):
        timeformat = console._log_render.time_format
        console._log_render.omit_repeated_times = False
        console._log_render.show_path = False
        dt = console.get_datetime()
        timesample = timeformat(dt) if callable(timeformat) else dt.strftime(timeformat)
        margin = len(timesample)
        self._r_url = max(len(addr.url) for addr in self.addresses)
        self._r_ext = 18  # extra space for markup, use [/] + spaces to fill
        fraction = "[yellow]({task.completed}/{task.total})"
        percentage = "[green]{task.percentage:>%i.3f}%%" % (margin - 1)
        description = "{task.description:<%i}" % (self._r_url + self._r_ext)
        self.progress = Progress(
            percentage,
            description,
            BarColumn(None),
            fraction,
            console=console,
            auto_refresh=False,
        )
        self.task = self.progress.add_task("Progress:", total=len(self.addresses))

    def pre_get(self, i: int, address: Address):
        desc = "[repr.url]" + address.url + "[reset]"
        self.progress.update(self.task, description=desc, completed=i, refresh=True)

    def post_get(self, address: Address, result: Result, ask_to_save=True):
        """handles the result, the corresponding output,
        and returns whether the user wants to continue"""

        if isinstance(result, KeyboardInterrupt):
            self.progress.stop()
            do_quit = console.input("[yellow]you [dark_orange]REALLY[/] wanna quit?: ")
            if do_quit and do_quit in "nN":
                self.progress.start()  # (continue)
                return True
            if ask_to_save:
                console.print("ok sure. [bar.pulse]just one last thing:...")
                do_save = console.input("[cyan]wanna update the results so far?: ")
                if not do_save or do_save not in "nN":
                    iofiles = parser.parse_known_args()[0]
                    self.save_results(iofiles.input, iofiles.output)
                    console.print("[green]done")
            return False
        elif not isinstance(result, BaseException):
            self.reached[result.url] = None  # add to the set-like object
            self.addresses.pop(Address(result.url))
            logger.info(result)
            out_main = result.status_code
        else:
            name = type(result).__name__
            key = abbv.get(name, "etc.")
            self.errstats[key] = self.errstats.get(key, 0) + 1
            logger.error(result)
            out_main = f"<{name}>"
        errs = " ".join(
            f"[dark_orange]{key}[reset]:[bar.pulse]{value}[/]"
            for key, value in self.errstats.items()
        )
        reached = f"[cyan]reached[reset]:[repr.str]{len(self.reached)}[/]"
        console.log(f"{address.url:<{self._r_url}}  {out_main:<27} {reached} {errs}")
        return True

    def _update_file(self, filename: str | Path, content: Iterable, overwrite=False):
        path = Path(filename)
        path.touch()
        with path.open("w" if overwrite else "a") as file:
            file.write("\n".join(content))

    def save_results(self, output_file: str, tested_file=None):
        self._update_file(output_file, self.reached)
        if tested_file:
            self._update_file(tested_file, self.addresses, True)


if __name__ == "__main__":
    args = parser.parse_args()
    with open(args.input) as file:
        domains = file.read().splitlines()
    checker = Reacheck(domains)
    try:
        checker.reachout()
    finally:
        checker.save_results(args.output, args.input)
