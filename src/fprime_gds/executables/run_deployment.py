from __future__ import print_function
import os
import sys
import time
import atexit
import argparse
import platform
import subprocess
import shutil
import distutils

# Try to import each GUI type, and if it can be imported
# it will be provided to the user as an option
GUIS = ["none"]
try:
    import fprime_gds.tkgui.tools.gse
    GUIS.append("tk")
except ImportError as exc:
    print("[WARNING] Could not import TK GUI: {0}:{1}".format(type(exc), str(exc), file=sys.stderr))
except SyntaxError as exc:
    print("[WARNING] TK GUI not supported in Python 3: {0}:{1}".format(type(exc), str(exc), file=sys.stderr))
try:
    import fprime_gds.wxgui.tools.gds
    GUIS.append("wx")
except ImportError as exc:
    print("[WARNING] Could not import WX GUI: {0}:{1}".format(type(exc), str(exc), file=sys.stderr))

def detect_terminal(title):
    '''
    Detect a terminal based on the OS.
    @param title: title to put on the terminal
    :return: terminal program
    '''
    if platform.system() == "Windows":
        return ["cmd.exe", "/C"]
    else:
        terminals = [["xterm", "-T", title, "-e"], ["lxterminal", "-t", title, "-e"],
                     ["gnome-terminal", "--title", title, "--"], ["Konsole", "-e"]]
        for terminal in terminals:
            try:
                if shutil.which(terminal[0]) is not None:
                    return terminal
            except AttributeError:
                if distutils.spawn.find_executable(terminal[0]) is not None:
                    return terminal
        else:
            error_exit("No terminal emulator found. Please install 'xterm'", 8)


def find_in(token, deploy, is_file=True, error=None):
    '''
    Find token in deploy directory by walking
    :param token: token to search for
    :param deploy: directory to start with
    :param is_file: true if looking for file, otherwise false
    :return: full path to token
    '''
    if not os.path.isdir(deploy):
        error_exit("{0} is not a directory".format(deploy), 3)
    for dirpath, dirs, files in os.walk(deploy):
        if (is_file and token in files) or (not is_file and token in dirs):
            return os.path.join(dirpath, token)
    #Fill in default error
    if error is None:
        error = "Failed to find {0} '{1}' under {2}".format("file" if is_file else "directory", token, deploy)
    error_exit(error, 4)


def get_args(args):
    '''
    Gets an argument parsers to read the command line and process the arguments. Return
    the arguments in their namespace.
    '''
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument("-g", "--gui", choices=GUIS, dest="gui", type=str,
                        help="Set the desired GUI system for running the deployment. [default: %default]",
                        default="tk")
    parser.add_argument("-p", "--port", dest="port", action="store", type=int,
                        help="Set the threaded TCP socket server port [default: %default]", default=50000)
    parser.add_argument("-a", "--addr", dest="addr", action="store", type=str,
                        help="set the threaded TCP socket server address [default: %default]", default="0.0.0.0")
    parser.add_argument("-n", "--no-app", dest="noapp", action="store_true",
                        help="Disables the compiled app from starting [default: %default]", default=False)
    parser.add_argument("-d", "--deployment", dest="deploy", action="store", required=False, type=str,
                        help="Path to deployment directory. Will be used to find dictionary and app automatically")
    parser.add_argument("--dictionary", dest="dictionary", action="store", required=False, type=str,
                        help="Path to dictionary. Overrides deploy if both are set")
    parser.add_argument("--app", dest="app", action="store", required=False, type=str,
                        help="Path to app to run. Overrides deploy if both are set. Ignored if -n is set.")
    parser.add_argument("-l", "--logs", dest="logs", action="store", default=None, type=str,
                        help="Logging directory. Created if non-existant.")
    # GUI specific items
    if "wx" in GUIS:
        parser.add_argument("-c", "--config", dest="config", action="store", default=None, type=str,
                            help="Configuration for wx GUI. Ignored if not using wx.")
    # Parse the arguments
    parsed_args = parser.parse_args(args)
    # Find the dictionary and app
    app = parsed_args.app
    dictionary = parsed_args.dictionary
    # If app is None, search deploy for it
    if app is None and parsed_args.deploy is not None:
        basename = os.path.basename(os.path.normpath(parsed_args.deploy))
        app = find_in(basename, parsed_args.deploy, is_file=True,
                      error="Could not find application '{0}' under {1}. Specify -a, build it, or run without using -n."
                      .format(basename, parsed_args.deploy))
    elif app is None:
        error_exit("--app or -d must be supplied to run app, or -n supplied to disable app", 2)
        raise Exception("EXIT FAILED")
        dictionary = parsed_args.dictionary
    elif not os.path.isfile(app):
        error_exit("App {0} is not file".format(app), 2)
        raise Exception("EXIT FAILED")
    # If dictionary is None, search deploy for it
    if dictionary is None and parsed_args.deploy is not None:
        dictionary = find_in("py_dict", parsed_args.deploy, is_file=False,
                      error="Could not find python dictionaries' under {0}. Specify --dictionary or build them."
                      .format(parsed_args.deploy))
    elif dictionary is None:
        error_exit("--dictionary or -d must be supplied to supply dictionary", 2)
        raise Exception("EXIT FAILED")
    elif not os.path.isdir(dictionary):
        error_exit("Dictionary {0} is not directory".format(app), 2)
        raise Exception("EXIT FAILED")
    # Fail-safe check
    if app is None or dictionary is None:
        error_exit("-d or --app and --dictionary must be supplied.", 3)
        raise Exception("EXIT FAILED")
    # Check and set GUI specifics
    if parsed_args.gui == "wx" and parsed_args.config is None and parsed_args.deploy is not None:
        parsed_args.config = find_in("gds.ini", parsed_args.deploy, is_file=True,
                      error="Could not gds.ini dictionaries' under {0}. Specify -c or create it."
                      .format(parsed_args.deploy))
    elif parsed_args.gui == "wx" and parsed_args.config is None:
        error_exit("wx GUI requires -c to be specified, or gse.ini in deployment specified with -d", 4)
    # Check and set GUI specifics
    if parsed_args.logs is None and parsed_args.deploy is not None:
        parsed_args.logs = os.path.join(parsed_args.deploy, "logs")
    elif parsed_args.logs is None:
        error_exit("Log directory -l or deployment dir -d write permission needed", 5)
    # Make log file
    if parsed_args.logs is not None:
        try:
            os.mkdir(parsed_args.logs)
        except Exception as ioe:
            if "exists" not in str(ioe).lower():
                error_exit("Failed to make directory for logs at {0} with error {1}".format(parsed_args.logs, ioe))
    return parsed_args, app, dictionary


def error_exit(error, code=1):
    '''
    Error this run, and exit cleanly.
    '''
    print("[ERROR] {0}".format(error), file=sys.stderr)
    sys.exit(code)


def launch_process(cmd, stdout=None, stderr=None, name=None):
    '''
    Launch a process in python
    :param cmd: command arguments to run
    :param stdout: standard out destination
    :param stderr: standard error destination
    :param name: (optional) short name for printing
    :return: running process
    '''
    if name is None:
        name = str(cmd)
    proc = subprocess.Popen(cmd, stdout=stdout, stderr=stderr)

    # When python exits, nuke this process
    def kill_wait():
        '''Kill process and wait for 2 seconds for it to die'''
        try:
            proc.kill()
            proc.wait()
        except OSError:
            pass
    atexit.register(kill_wait)
    print("[INFO] Waiting 2 seconds for {0} to start".format(name))
    time.sleep(2)
    proc.poll()
    if proc.returncode is not None:
        error_exit("Failed to start {0}".format(name), 1)
        raise Exception("FAILED TO EXIT")
    return proc


def launch_tts(port, address, logs):
    '''
    Launch the Threaded TCP Server
    :param port: port to attach to
    :param address: address to bind to
    :param logs: logs output directory
    :return: process
    '''
    # Open log, and prepare to close it cleanly on exit
    tts_log = open(os.path.join(logs, "ThreadedTCP.log"), 'w')
    atexit.register(lambda: tts_log.close())
    # Launch the tcp server
    tts_cmd = ["python", "-u", "-m", "fprime_gds.executables.tcpserver", "--port", str(port), "--host", str(address)]
    return launch_process(tts_cmd, stdout=tts_log, stderr=subprocess.STDOUT, name="TCP Server")


def launch_tk(port, dictionary, address, log_dir):
    '''
    Launch the GSE
    :param port: port to connect to
    :param dictionary: dictionary to use
    :param address: dictionary to connect to
    :param log_dir: directory to log to
    :return: process
    '''
    gse_args = ["python", "-u", "-m", "fprime_gds.tkgui.tools.gse", "--port", str(port), "--dictionary", dictionary,
                "--connect", "--addr", address, "-L", log_dir]
    return launch_process(gse_args, name="TK GUI")


def launch_wx(port, dictionary, address, log_dir, config):
    '''
    Launch the GDS gui
    :param port: port to connect to
    :param dictionary: dictionary to look at
    :param address: address to connect to
    :param log_dir: directory to place logs
    :param config: configuration to use
    :return: process
    '''
    gse_args = ["python", "-u", "-m", "fprime_gds.wxgui.tools.gds", "--port", str(port), "--dictionary", dictionary,
                "--addr", address, "-L", log_dir, "--config", config]
    return launch_process(gse_args, name="WX GUI")


def launch_app(app, port, address):
    '''
    Launch the app
    :param app: application to launch
    :param port: port to connect to
    :param address: address to connect to
    :return: process
    '''
    name = "{0} Application".format(os.path.basename(app))
    app_cmd = detect_terminal(name)
    app_cmd.extend([os.path.abspath(app), "-p", str(port), "-a", address])
    return launch_process(app_cmd, name=name)


def main(argv=None):
    '''
    Main function used to launch processes.
    '''
    wait_proc = None
    args, app, dictionary = get_args(argv)

    # Launch TTS and ensure it starts w/o error
    launch_tts(args.port, args.addr, args.logs)
    # Launch a gui, if specified
    address = args.addr
    if address == "0.0.0.0":
        address = "127.0.0.1"
    # Launch the desired GUI package
    if args.gui == "tk":
        wait_proc = launch_tk(args.port, dictionary, address, args.logs)
    elif args.gui == "wx":
        wait_proc = launch_wx(args.port, dictionary, address, args.logs, args.config)
    elif args.gui == "none":
        print("[WARNING] No GUI specified, running headless", file=sys.stderr)
    else:
        raise Exception("Invalid GUI specified: {0}".format(args.gui))
    # Run app if specified
    if not args.noapp:
        app_proc = launch_app(app, args.port, address)
    # Determine waitable item
    if wait_proc is None:
        wait_proc = app_proc
    # Wait for either gui or app to finish, then close
    try:
        wait_proc.wait()
    except KeyboardInterrupt:
        print("[INFO] CTRL-C received. Exiting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
