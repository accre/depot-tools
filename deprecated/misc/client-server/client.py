#!/usr/bin/env python

import xmlrpclib

#server = xmlrpclib.Server('https://localhost:16309')
#server = xmlrpclib.Server('https://huginn.vampire:16309')
server = xmlrpclib.Server('http://huginn.vampire:16309')

print server.add(1,2)
print server.div(10,4)
print server.mult(2,4)
