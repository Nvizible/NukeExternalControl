Nuke External Control

This allows you to call Nuke Python commands from outside Nuke


Installation
============
All of the necessary files are contained in the nukeExternalControl
Python package.

Make sure the directory containing the package is somewhere in $NUKE_PATH.

Also, be sure to add it to the $PYTHONPATH of any Python interpreters you
want to have access to the client interface.

To start a command sever whenever Nuke is launched, add the following lines
to your Nuke menu.py:
---------------------------
import nukeExternalControl.server
nukeExternalControl.server.nuke_command_server()
---------------------------


Usage
=====
To initialise the external end, run the following (while Nuke is running with an
active command server):
---------------------------
import nukeExternalControl.client
conn = nukeExternalControl.client.NukeConnection()
nuke = conn.nuke
---------------------------

From that point on, you can run anything that you would inside Nuke from outside:
---------------------------
for n in nuke.selectedNodes():
	print n.name()
	n['disable'].setValue(True)

blur = nuke.createNode("Blur")
---------------------------

If you need to import a module inside Nuke, you can run:
---------------------------
nukescripts = conn.import_module("nukescripts")
---------------------------

You can also use the server.py submodule as input to a terminal instance of
Nuke in order to launch a server without opening a full GUI copy of Nuke.
---------------------------
Nuke -t <somePath>/nukeExternalControl/server.py
---------------------------

    where <somePath> represents the path to the directory containing the package.

Note that this will block the Nuke process, meaning the user will not be able to
use the Nuke terminal as a Python interpreter as they normally would. In this
case, the server can be shut down at any time by calling the client's
'.shutdown_server()' method.
---------------------------
import nukeExternalControl.client
conn = nukeExternalControl.client.NukeConnection()
nuke = conn.nuke
#
# <do some stuff in Nuke here>
#
conn.shutdown_server()
---------------------------


Command Manager Interface
=========================
The Nuke Command Manager is a special wrapper for the client-server interface
that is designed to be used in a "with" statement. It does not require you to
launch and manage a separate instance of Nuke, but handles this transparently
and allows you to take advantage of Nuke's Python environment for the duration
of the "with" block.

To use it, you may need to edit the common.py file in the package directory.
Find the line that says:
---------------------------
    NUKE_EXEC = 'Nuke'
---------------------------
This string defines the shell command you would use to launch Nuke (with any
flags excluded). You should edit this so that, if you were to open a new
terminal or command prompt and type in that string, Nuke would be launched.

After that has been set, a sample use of the command manager is as follows:
---------------------------
from __future__ import with_statement
import nukeExternalControl.client

with nukeExternalControl.client.NukeCommandManager() as conn:
    nuke = conn.nuke
    b = nuke.createNode("Blur")
    print b.writeKnobs()
---------------------------

Once the "with" block has finished executing, the instance of Nuke that
was launched to provide access to the nuke module is closed down, so any
references to 'nuke' or any other variables in that remote namespace will
result in exceptions.

