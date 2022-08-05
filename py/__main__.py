# coding: utf-8
# @author octopoulo <polluxyz@gmail.com>
# @version 2022-08-03

"""
Main
"""

from argparse import ArgumentParser

from pong_client import MainClient
from pong_common import VERSION
from pong_server import MainServer


def main():
	parser = ArgumentParser(description='Battle Pong', prog='python __main__.py')
	add    = parser.add_argument

	add('--fps'        , nargs='?', default=0          , const=120    , type=int  , help='FPS limit')
	add('--host'       , nargs='?', default='127.0.0.1',                type=str  , help='Server address')
	add('--interpolate', nargs='?', default=1          , const=1      , type=int  , help='Interpolate physics')
	add('--port'       , nargs='?', default=9000       ,                type=int  , help='Server port')
	add('--protocol'   , nargs='?', default='tcp'      , const='tcp'  , type=str  , help='Network protocol', choices=['tcp', 'udp'])
	add('--reconnect'  , nargs='?', default=3          ,                type=float, help='Reconnect every x sec')
	add('--renderer'   , nargs='?', default='basic'    , const='basic', type=str  , help='Renderer to use', choices=['basic', 'opengl'])
	add('--server'     , nargs='?', default=0          , const=1      , type=int  , help='Run a server')
	add('--size'       , nargs='?', default=1280       ,                type=int  , help='Resolution')
	add('--version'    , nargs='?', default=0          , const=1      , type=int  , help='Show the version')

	args    = parser.parse_args()
	kwargs  = vars(args)
	argsSet = set(item for item, value in kwargs.items() if value)

	if argsSet & {'version'}:
		print(VERSION)
	elif argsSet & {'server'}:
		MainServer(**kwargs)
	else:
		MainClient(**kwargs)


if __name__ == '__main__':
	main()
