# coding: utf-8
# @author octopoulo <polluxyz@gmail.com>
# @version 2022-08-02

"""
Pong server
"""

from itertools import chain
from math import sqrt
import signal
import struct
from typing import List

import pyuv

from pong_common import Ball, Body, Paddle, Pong


class PongServer(Pong):
	def __init__(self, **kwargs):
		super(PongServer, self).__init__(**kwargs)
		print('PongServer', kwargs)

		self.connId  = 0
		self.id      = 0
		self.players = {}
		self.running = True
		self.server  = None                                 # type: pyuv.TCP
		self.slots   = [None, None, None, None]

		self.loop     = pyuv.Loop.default_loop()
		self.signal_h = pyuv.Signal(self.loop)

	# HELPERS
	#########

	def AddPlayer(self, client: pyuv.TCP, wantSlot: int) -> int:
		ip, port = client.getpeername()
		slot     = self.FindSlot(wantSlot)
		if slot < len(self.slots): self.slots[slot] = client
		self.players[client] = [slot, ip, port, 0, 0, 0]
		print('AddPlayer: players=')
		self.PrintPlayers()
		return slot

	def DeletePlayer(self, client: pyuv.TCP):
		if player := self.players.get(client):
			self.slots[player[0]] = None
			del self.players[client]
			print('DeletePlayer: players=')
			self.PrintPlayers()

	def FindSlot(self, wantSlot: int) -> int:
		numSlot = len(self.slots)
		if 0 <= wantSlot <= numSlot and not self.slots[wantSlot]: return wantSlot

		for i, slot in enumerate(self.slots):
			if not slot: return i
		# spectator
		return numSlot

	def PrintPlayers(self):
		print(self.slots)
		for key, value in self.players.items():
			print(' ', key, value)

	# NETWORK
	#########

	def OnConnect(self, server: pyuv.TCP, error: int):
		self.connId += 1
		client = pyuv.TCP(self.loop)
		self.server.accept(client)
		client.start_read(self.OnRead)

	def OnRead(self, client: pyuv.TCP, data: bytes, error: int):
		if data is None:
			client.close()
			self.DeletePlayer(client)
			return

		player = self.players.get(client)
		pid    = player[0] if player else -1

		while len(data):
			if data[0] == 0:
				# 1) game
				# ball
				if data[1] == ord('B'):
					bid = data[2]
					if 0 <= bid < len(self.balls):
						self.balls[bid].Parse(data[:Ball.structSize])
						self.dirtyBall |= (1 << bid)

					data = data[Ball.structSize:]

				# paddle
				elif data[1] == ord('P'):
					pid = data[2]
					if 0 <= pid < len(self.paddles):
						message = data[:Paddle.structSize]
						self.paddles[pid].Parse(message)
						self.dirtyPaddle |= (1 << pid)

					data = data[Paddle.structSize:]

				# 2) connection
				elif data[1] == ord('I'):
					wantSlot = data[2]
					if pid < 0: pid = self.AddPlayer(client, wantSlot)
					self.Send(client, struct.pack('xBB', ord('I'), pid))

					for obj in chain(self.balls, self.paddles): self.Send(client, obj.Format())
					for id, wall in enumerate(self.walls): self.Send(client, struct.pack('xBBB', ord('W'), id, wall))

					data = data[3:]

				else:
					print(f'player_{pid}:', data)
			else:
				if data[0: 5] == b'GET /':
					i = 5
					size = len(data)
					while i < size:
						if data[i] == 0:
							data = data[i:]
							break
						i += 1

					if i == size: data = data[i:]

					speed = self.balls[0].body.linearVelocity
					html  = ''.join([
						'<html>',
						'<body>',
							'<h1>Battle Pong</h1>',
							f'<div>Balls: {len(self.balls)}</div>',
							f'<div>Players: {len(self.players)}</div>',
							f'<div>Speed: {sqrt(speed[0] * speed[1] + speed[1] * speed[1])}</div>',
						'</body>',
						'</html>',
					])

					response = '\r\n'.join([
						'HTTP/1.1 200 OK',
						'Date: Sun, 18 Oct 2012 10:36:20 GMT',
						'Server: Custom/1.0.0',
						f'Content-Length: {len(html) + 4}',
						'Content-Type: text/html; charset=UTF-8',
						'',
						html,
						'<html><body><h1>Hello there!</h1></body></html>',
						'',
						'',
					])
					self.Send(client, response)
					self.DeletePlayer(client)
				else:
					print(f'player_{pid}:', data)
					break

	def ShareObjects(self, objects: List[Body], flag: int, skipId: int = -1):
		for oid, obj in enumerate(objects):
			if flag == -1 or (flag & (1 << oid)):
				message = obj.Format()
				for sid, slot in enumerate(self.slots):
					if slot and sid != skipId and obj.parentId != sid:
						self.Send(slot, message)

	def ShareWalls(self, flag: int):
		for id, wall in enumerate(self.walls):
			if flag == -1 or (flag & (1 << id)):
				message = struct.pack('xBBB', ord('W'), id, wall)
				for slot in self.slots:
					if slot: self.Send(slot, message)

	def Signal(self, handle: pyuv.Signal, signum: int):
		for client in self.players:
			try:
				client.close()
			except:
				pass

		self.signal_h.close()
		self.server.close()
		self.running = False

	# GAME
	######

	def NewGame(self, numDiv: int = 0):
		super(PongServer, self).NewGame(numDiv)

		for slot in self.slots:
			if slot and (player := self.players.get(slot)):
				player[0] = 1

		self.ShareObjects(self.balls, -1)
		self.ShareObjects(self.paddles, -1)
		self.ShareWalls(-1)

	# MAIN LOOP
	###########

	def Run(self):
		self.server = pyuv.TCP(self.loop)
		self.server.bind((self.host, self.port))
		self.server.listen(self.OnConnect)
		self.connected = True

		self.signal_h.start(self.Signal, signal.SIGINT)

		self.NewGame()
		self.AddBall(1)

		while self.running:
			self.PhysicsLoop()
			self.loop.run(pyuv.UV_RUN_NOWAIT)

			if self.dirtyBall:   self.ShareObjects(self.balls, self.dirtyBall)
			if self.dirtyPaddle: self.ShareObjects(self.paddles, self.dirtyPaddle)
			if self.dirtyWall:   self.ShareWalls(self.dirtyWall)


def MainServer(**kwargs):
	print(f'Server: pyuv={pyuv.__version__}')
	server = PongServer(**kwargs)
	server.Run()
	print('Goodbye.')


if __name__ == '__main__':
	MainServer()
