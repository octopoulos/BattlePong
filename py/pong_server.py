# coding: utf-8
# @author octopoulo <polluxyz@gmail.com>
# @version 2022-08-04

"""
Pong server
"""

from itertools import chain
from math import sqrt
import signal
import struct
from time import time
from typing import List, Tuple

import pyuv

from pong_common import Ball, Body, Paddle, Pong, TIMEOUT_DISCONNECT, TIMEOUT_PING, UdpHeader


class PongServer(Pong):
	def __init__(self, **kwargs):
		super(PongServer, self).__init__(**kwargs)
		print('PongServer', kwargs)

		self.connId    = 0
		self.id        = 0
		self.players   = {}
		self.running   = True
		self.serverTcp = None                               # type: pyuv.TCP
		self.serverUdp = None                               # type: pyuv.UDP
		self.slots     = [None, None, None, None]

		self.loop      = pyuv.Loop.default_loop()
		self.signal_h  = pyuv.Signal(self.loop)

	# HELPERS
	#########

	def AddPlayer(self, address: Tuple[str, int], wantSlot: int) -> int:
		slot = self.FindSlot(wantSlot)
		if slot < len(self.slots): self.slots[slot] = address
		self.players[address] = [slot, time(), time()]
		print('AddPlayer: players=')
		self.PrintPlayers()
		return slot

	def CheckPlayers(self):
		now     = time()
		removes = set()

		for address, player in self.players.items():
			if now > player[1] + TIMEOUT_DISCONNECT:
				removes.add(address)
			elif now > player[1] + TIMEOUT_PING and now > player[2] + TIMEOUT_PING:
				self.Send(address, b'p')
				player[2] = now

		if removes:
			for remove in removes: self.DeletePlayer(remove, False)
			self.PrintPlayers()

	def DeletePlayer(self, address: Tuple[str, int], log: bool = True):
		if player := self.players.get(address):
			self.slots[player[0]] = None
			del self.players[address]
			print(f'DeletePlayer: {address}')
			if log: self.PrintPlayers()

	def FindSlot(self, wantSlot: int) -> int:
		numSlot = len(self.slots)
		if 0 <= wantSlot <= numSlot and not self.slots[wantSlot]: return wantSlot

		for i, slot in enumerate(self.slots):
			if not slot: return i
		# spectator
		return numSlot

	def PrintPlayers(self):
		print('slots=', self.slots)
		for key, value in self.players.items():
			print(' ', key, value)

	# NETWORK
	#########

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
				message = struct.pack('BBB', ord('W'), id, wall)
				for slot in self.slots:
					if slot: self.Send(slot, message)

	def Signal(self, handle: pyuv.Signal, signum: int):
		for client in self.players:
			try:
				client.close()
			except:
				pass

		self.signal_h.close()

		if self.serverTcp:
			self.serverTcp.close()
			self.serverTcp = None

		if self.serverUdp:
			self.serverUdp.close()
			self.serverUdp = None

		self.running = False

	def TcpListen(self, server: pyuv.TCP, error: int):
		self.connId += 1
		client = pyuv.TCP(self.loop)
		self.serverTcp.accept(client)
		client.start_read(self.TcpServerRead)

	def TcpServerRead(self, client: pyuv.TCP, data: bytes, error: int):
		if data is None: return

		while len(data):
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
				client.write(response.encode())
			else:
				print(f'TcpServerRead:', data)
				break

	def UdpOnRead(self, handle: pyuv.UDP, address: Tuple[str, int], flags: int, data: bytes, error: int):
		if data is None: return

		seq = self.udpHeader.Parse(data[:UdpHeader.structSize])
		if seq < self.seqRecv and (self.seqRecv < 64512 or seq > 1024):
			print('seq=', seq, '<', self.seqRecv)
		else:
			self.seqRcv = seq

		data = data[UdpHeader.structSize:]

		player = self.players.get(address)
		if player:
			pid       = player[0]
			player[1] = time()
		else:
			pid = -1

		# 1) game
		# ball
		if data[0] == ord('B'):
			bid = data[1]
			if 0 <= bid < len(self.balls):
				self.balls[bid].Parse(data[:Ball.structSize])
				self.dirtyBall |= (1 << bid)

		# paddle
		elif data[0] == ord('P'):
			pid = data[1]
			if 0 <= pid < len(self.paddles):
				message = data[:Paddle.structSize]
				self.paddles[pid].Parse(message)
				self.dirtyPaddle |= (1 << pid)

		# 2) connection
		elif data[0] == ord('p'): self.Send(address, b'q')
		elif data[0] == ord('q'):
			print('pong!', pid, address, player)

		elif data[0] == ord('I'):
			wantSlot = data[1]
			if pid < 0: pid = self.AddPlayer(address, wantSlot)
			self.Send(address, struct.pack('BB', ord('I'), pid))

			for obj in chain(self.balls, self.paddles): self.Send(address, obj.Format())
			for id, wall in enumerate(self.walls): self.Send(address, struct.pack('BBB', ord('W'), id, wall))
		else:
			print(f'UdpOnRead_{pid}:', data)

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
		self.serverTcp = pyuv.TCP(self.loop)
		self.serverTcp.nodelay(True)
		self.serverTcp.bind((self.host, self.port + 80))
		self.serverTcp.listen(self.TcpListen)

		self.udpHandle = pyuv.UDP(self.loop)
		self.udpHandle.bind(('127.0.0.1', 9000))
		self.udpHandle.start_recv(self.UdpOnRead)

		self.signal_h.start(self.Signal, signal.SIGINT)

		self.NewGame()
		self.AddBall(1)

		while self.running:
			self.PhysicsLoop()
			self.loop.run(pyuv.UV_RUN_NOWAIT)

			if self.dirtyBall:   self.ShareObjects(self.balls, self.dirtyBall)
			if self.dirtyPaddle: self.ShareObjects(self.paddles, self.dirtyPaddle)
			if self.dirtyWall:   self.ShareWalls(self.dirtyWall)

			self.CheckPlayers()


def MainServer(**kwargs):
	print(f'Server: pyuv={pyuv.__version__}')
	server = PongServer(**kwargs)
	server.Run()
	print('Goodbye.')


if __name__ == '__main__':
	MainServer()
