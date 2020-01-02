from __future__ import print_function

import urllib2, urllib
import argparse
import time
import os
import json
import sys
from urlparse import urlparse
from datetime import date
from utils import stringjoin, mkdir_p
from generators import html, query, schema

# Hack-ish way to handle unicode (finger crossed)
reload(sys)
sys.setdefaultencoding('UTF8')


def wrap_exit(method, exceptions = (OSError, IOError)):
    def fn(*args, **kwargs):
        try:
            print(reset)
            return method(*args, **kwargs)
        except exceptions:
            sys.exit('Can\'t open \'{0}\'. Error #{1[0]}: {1[1]}'.format(args[0], sys.exc_info()[1].args))

    return fn
exit = wrap_exit(exit)

# colors for terminal messages
red = ""
green = ""
white = ""
yellow = ""
reset = ""

def posix_colors():
    global red, green, white, yellow, reset
    red = "\033[1;31;10m[!] "
    green = "\033[1;32;10m[+] "
    white = "\033[1;37;10m"
    yellow = "\033[1;33;10m[!] "
    reset = "\033[0;0m"

def supports_color():
    """
    Returns True if the running system's terminal supports color, and False
    otherwise.
    """
    plat = sys.platform
    supported_platform = plat != 'Pocket PC' and (plat != 'win32' or
                                                  'ANSICON' in os.environ)
    # isatty is not always implemented, #6223.
    is_a_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    return supported_platform and is_a_tty

if supports_color():
    posix_colors()


def query_result(target, key, proxyDict):
    """
    Execute the introspection query against the GraphQL endpoint

    :param target:
        Expects a valid URL ex. https://example.com/graphql
        Raise an exception if HTTP/HTTPS schema is missing

    :param key:
        Optional parameter to be used as authentication header
        "Basic dXNlcjp0ZXN0"
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"

    :param proxyDict:
        Optional parameter to be used as web proxy to go through
        ex. http://127.0.0.1:8080

    :return:
        Returns a dictionary objects to be parsed
    """
    # Introspection Query
    # -----------------------
    introspection_query =  "query IntrospectionQuery{__schema{queryType{name}mutationType{name}subscriptionType{name}types{...FullType}directives{name description locations args{...InputValue}}}}fragment FullType on __Type{kind name description fields(includeDeprecated:true){name description args{...InputValue}type{...TypeRef}isDeprecated deprecationReason}inputFields{...InputValue}interfaces{...TypeRef}enumValues(includeDeprecated:true){name description isDeprecated deprecationReason}possibleTypes{...TypeRef}}fragment InputValue on __InputValue{name description type{...TypeRef}defaultValue}fragment TypeRef on __Type{kind name ofType{kind name ofType{kind name ofType{kind name ofType{kind name ofType{kind name ofType{kind name ofType{kind name}}}}}}}}"
    old_introspection_query =  "query IntrospectionQuery{__schema{queryType{name}mutationType{name}subscriptionType{name}types{...FullType}directives{name description args{...InputValue}onOperation onFragment onField}}}fragment FullType on __Type{kind name description fields(includeDeprecated:true){name description args{...InputValue}type{...TypeRef}isDeprecated deprecationReason}inputFields{...InputValue}interfaces{...TypeRef}enumValues(includeDeprecated:true){name description isDeprecated deprecationReason}possibleTypes{...TypeRef}}fragment InputValue on __InputValue{name description type{...TypeRef}defaultValue}fragment TypeRef on __Type{kind name ofType{kind name ofType{kind name ofType{kind name}}}}"
    # -----------------------
    if key:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:55.0) Gecko/20100101 Firefox/55.0",
            "Authorization": key
            # TODO add the option for custom headers and variables
        }
    else:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:55.0) Gecko/20100101 Firefox/55.0"
        }
    try:
        # Issue the Introspection request against the GraphQL endpoint
        data = urllib.urlencode({"query": introspection_query})
        if proxyDict:
            proxy = urllib2.ProxyHandler(proxyDict)
            opener = urllib2.build_opener(proxy)
            urllib2.install_opener(opener)
        request = urllib2.Request(target, data, headers=headers)
        contents = urllib2.urlopen(request).read()
        return contents

    except urllib2.HTTPError, e:
        print(stringjoin(red, str(e), reset))

    except urllib2.URLError, e:
        print(stringjoin(red, str(e), reset))


def main():
    """
    Query a GraphQL endpoint with introspection in order to retrieve the documentation of all the Queries, Mutations & Subscriptions.
    It will also generate Queries, Mutations & Subscriptions templates (with optional placeholders) for all the known types.

    :return:
        none
    """
    # Args parser definition
    # -----------------------
    parser = argparse.ArgumentParser(prog="inql", description="GraphQL Scanner")
    parser.add_argument("-t", default=None, dest="target",
                        help="Remote GraphQL Endpoint (https://<Target_IP>/graphql)")
    parser.add_argument("-f", dest="schema_json_file", default=None, help="Schema file in JSON format")
    parser.add_argument("-k", dest="key", help="API Authentication Key")
    parser.add_argument('-p', dest="proxy", default=None,
                        help='IP of web proxy to go through (http://127.0.0.1:8080)')
    parser.add_argument("-d", dest="detect", action='store_true', default=False,
                        help="Replace known GraphQL arguments types with placeholder values (useful for Burp Suite)")
    parser.add_argument("-o", dest="output_directory", default=os.getcwd(),
                        help="Output Directory")
    args = parser.parse_args()
    # -----------------------

    mkdir_p(args.output_directory)
    os.chdir(args.output_directory)

    return init(args, lambda: parser.print_help())


def init(args, print_help=None):
    # At least one between -t or -f (target) parameters must be set
    if args.target is None and args.schema_json_file is None:
        print(stringjoin(red, "Remote GraphQL Endpoint OR a Schema file in JSON format must be specified!", reset))
        if print_help:
            print_help()
            exit(1)

    # Only one of them -t OR -f :)
    if args.target is not None and args.schema_json_file is not None:
        print(stringjoin(red, "Only a Remote GraphQL Endpoint OR a Schema file in JSON format must be specified, not both!", reset))
        if print_help:
            print_help()
            exit(1)

    # Takes care of any configured proxy (-p param)
    if args.proxy is not None:
        print(stringjoin(yellow, "Proxy ENABLED: ", args.proxy, reset))
        proxyDict = {"http": args.proxy, "https": args.proxy}
    else:
        proxyDict = {}

    if args.target is not None or args.schema_json_file is not None:
        if args.target is not None:
            # Acquire GraphQL endpoint URL as a target
            URL = urlparse(args.target).netloc
        else:
            # Acquire a local JSON file as a target
            print(stringjoin(yellow, "Parsing local schema file", reset))
            URL = "localschema"
        if args.detect:
            print(stringjoin(yellow, "Detect arguments is ENABLED, known types will be replaced with placeholder values", reset))
        # Used to generate 'unique' file names for multiple documentation
        timestamp = str(int(time.time()))  # Can be printed with: str(int(timestamp))
        today = str(date.today())
        # -----------------------
        # Custom Objects are required for fields names in the documentation and templates generation
        # old -c parameter, enabled by default
        custom = True
        # Generate the documentation for the target
        if args.target is not None:
            # Parse response from the GraphQL endpoint
            argument = query_result(args.target, args.key, proxyDict)
            # returns a dict
            argument = json.loads(argument)
        else:
            # Parse the local JSON file
            with open(args.schema_json_file, "r") as s:
                result_raw = s.read()
                argument = json.loads(result_raw)

        schema.generate(argument,
                        fpath=os.path.join(URL, "schema-%s-%s.json" % (today, timestamp)))
        html.generate(argument,
                      fpath=os.path.join(URL, "doc-%s-%s.html" % (today, timestamp)),
                      custom=custom,
                      target=args.target)
        query.generate(argument,
                       qpath=os.path.join(URL, "%s", today, timestamp, "%s"),
                       detect=args.detect,
                       custom=custom,
                       green_print=lambda s: print(stringjoin(green, "Writing Queries Templates", reset)))

    else:
        # Likely missing a required arguments
        print("Missing Arguments")
        if print_help:
            print(white)
            print_help()
            print(reset)
            exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Catch CTRL+C, it will abruptly kill the script
        print(stringjoin(red, "Exiting...", reset))
