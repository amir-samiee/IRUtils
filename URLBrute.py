import requests, warnings, logging, sys
from rich.console import Console
from typing import TypeAlias
from pathlib import Path

console = Console()
logger = logging.getLogger()
logfile = Path(__file__).parent / ".log"
logging.basicConfig(filename=logfile, level=0)
Result: TypeAlias = requests.Response | BaseException


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
    def __init__(self, addresses: list[str]):
        self.addresses = list(map(Address, addresses))
        self.timeout = 5
        self.errors = {}
        self.reachable = set()

        maxurllen = max(map(len, self.addresses))
        counterlen = len(str(len(addresses)))
        raw = "{:>%i}/%i: {:<%i}  ..."
        self.pg_template = raw % (counterlen, len(addresses), maxurllen)

    def reachout(self):
        for i, addr in enumerate(self.addresses, 1):
            self.pre_get(i, addr)
            result = addr.get(timeout=self.timeout)
            do_continue = self.post_get(result)
            if do_continue is False:
                break

    def _update_success(self, response: requests.Response):
        console.print(f"[repr.str]{response.status_code}".ljust(37), end=" ")
        self.reachable.add(response.url)
        logger.info(response)

    def _update_failure(self, err: BaseException):
        key = type(err).__name__
        console.print(f"<{key}>".ljust(27), end=" ")
        self.errors[key] = self.errors.get(key, 0) + 1
        logger.error(err)

    def post_get(self, result: Result):
        """handles the result, the corresponding output,
        and returns whether the user wants to continue"""

        # NOTE: we're not using the console
        # here as it doesn't respond to "\b"
        print("\b" * 3, end="")

        if isinstance(result, KeyboardInterrupt):
            confirm = console.input("wanna continue?: ")
            if confirm.lower() in "nq":
                return False
        elif isinstance(result, BaseException):
            self._update_failure(result)
        else:
            self._update_success(result)
        console.print(self.errors)
        return True

    def pre_get(self, i: int, address: Address):
        console.print(self.pg_template.format(i, address.url), end="")
        # TODO: progress bar


if __name__ == "__main__":
    domainfile = sys.argv[-1] if len(sys.argv) > 1 else "domains.txt"
    with open(Path(__file__).parent / domainfile) as file:
        domains = file.read().split()
    checker = Reacheck(domains)
    checker.reachout()
