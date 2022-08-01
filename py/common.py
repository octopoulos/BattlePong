# coding: utf-8
# @author octopoulo <polluxyz@gmail.com>
# @version 2022-07-30

"""
Common functions
"""


def DefaultInt(value: int or str, default: int = None):
	if isinstance(value, int): return value
	if value is None: return default

	try:
		value = int(float(value))
	except (TypeError, ValueError):
		value = default

	return value
