# coding: utf-8
# @author octopoulo <polluxyz@gmail.com>
# @version 2022-07-29

"""
Main
"""

from argparse import ArgumentParser

from pong_client import MainClient
from pong_server import MainServer


def main():
	parser = ArgumentParser(description='Battle Pong', prog='python __main__.py')
	add = parser.add_argument

	add('--server', nargs='?', default=0, const=1, type=int, help='Run a server')

	args = parser.parse_args()
	args_dict = vars(args)
	args_set = set(item for item, value in args_dict.items() if value)

	if args_set & {'server'}:
		MainServer()
	else:
		MainClient()


if __name__ == '__main__':
	main()
