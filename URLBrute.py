from rich_argparse_plus import RichHelpFormatterPlus
from rich.progress import Progress, BarColumn
from typing import Iterable, TypeAlias
from argparse import ArgumentParser
import requests, warnings, logging
from rich import get_console
from pathlib import Path

console = get_console()
logger = logging.getLogger()
FILEDIR = Path(__file__).parent
Result: TypeAlias = requests.Response | BaseException
logging.basicConfig(filename=FILEDIR / ".log", level=0)

parser = ArgumentParser(allow_abbrev=True, formatter_class=RichHelpFormatterPlus)
style_modify = {"argparse.metavar": "yellow", "argparse.prog": "bold green"}
parser.add_argument("--output", default=FILEDIR / "results.txt")
parser.add_argument("--input", default=FILEDIR / "domains.txt")
RichHelpFormatterPlus.styles.update(style_modify)


class Address(str):
    pro = "https://"

    def __init__(self, value=""):
        if "." not in value:
            msg = "%s doesn't actually seem like a real web address to me" % repr(self)
            warnings.warn(msg)
        self._url = self if self.was_url else self.pro + self
        super().__init__()

    @property
    def domain(self):
        return self.url[len(self.pro) :]

    @property
    def url(self):
        return self._url

    def get(self, *args, **kwargs) -> Result:
        try:
            response = requests.get(self.url, *args, **kwargs)
        except BaseException as err:
            return err
        return response

    @property
    def was_url(self):
        return self.startswith(self.pro)

    def __len__(self):
        return len(self.url)


class Reacheck:
    def __init__(self, addresses: list[str], timeout=5.0):
        self.addresses = list(map(Address, addresses))
        self.timeout = timeout
        self.errors = {}
        self.reachable = set()

    def reachout(self):
        self._init_progress()
        with self.progress:
            for i, addr in enumerate(self.addresses, 1):
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
        self._r_url = max(map(len, self.addresses))
        self._r_ext = 18  # extra space for markup, use [/] + spaces to fill
        fraction = "[yellow]({task.completed}/{task.total})"
        percentage = "[green]{task.percentage:>%i.3f}%%" % (margin - 1)
        description = "{task.description:<%i}" % (self._r_url + self._r_ext)
        self.progress = Progress(
            percentage,
            description,
            BarColumn(89),
            fraction,
            console=console,
            auto_refresh=False,
        )
        self.task = self.progress.add_task("Progress:", total=len(self.addresses))

    def pre_get(self, i: int, address: Address):
        desc = "[repr.url]" + address.url + "[reset]"
        self.progress.update(self.task, description=desc, completed=i, refresh=True)

    def post_get(self, address: Address, result: Result):
        """handles the result, the corresponding output,
        and returns whether the user wants to continue"""

        if isinstance(result, KeyboardInterrupt):
            self.progress.stop()
            do_quit = console.input("do you REALLY wanna quit?: ")
            if do_quit in "nN":
                self.progress.start()  # (re-start)
                return True
            console.print("ok sure. just one last thing:...")
            do_save = console.input("do you wanna update the results so far?: ")
            if do_save not in "nN":
                # we're not going to mess with the actual input/output files here
                # TODO: resolve the issue above, preferably in Self.save_results itself
                self.save_results(parser.get_default("output"))
                console.print("done")
            return False
        elif isinstance(result, BaseException):
            key = type(result).__name__
            self.errors[key] = self.errors.get(key, 0) + 1
            logger.error(result)
            out = f"<{key}>"
        else:
            self.reachable.add(result.url)
            logger.info(result)
            out = result.status_code

        console.log(f"{address.url:<{self._r_url}}  {out:<27} {self.errors}")
        return True

    def _update_file(self, filename: str | Path, content: Iterable, remove=False):
        path = Path(filename)
        path.touch()
        with path.open("r+") as file:
            old = file.read().splitlines()
            a, b = map(set, (old, content))
            new = a - b if remove else a | b
            file.seek(0)
            file.write("\n".join(new))
            file.truncate()

    def save_results(self, output_file: str, tested_file=None):
        self._update_file(output_file, self.reachable)
        if tested_file:
            self._update_file(tested_file, self.reachable, True)


if __name__ == "__main__":
    args = parser.parse_args()
    with open(args.input) as file:
        domains = file.read().splitlines()
    checker = Reacheck(domains)
    checker.reachout()
    checker.save_results(args.output, args.input)
