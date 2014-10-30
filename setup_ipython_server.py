
"""
Set up an ipython notebook profile for use over the web on GVL servers.

After running this script, change to your project directory and run

   ipython notebook --profile=nbserver

This script will:
* Create a profile (nbserver) to use for the notebook server
* Configure password protection
* Configure the location and port to run behind our NGINX port forwarding
* Install the Table of Contents plugin
* Install MathJax locally

This script can be run by an individual non-sudo user to configure an
nbserver profile in their own account.

Under the default configuration, only ONE user can run IPython Notebook at a time,
as we are taking advantage of a single forwarded port. If you have multiple users, you
may want to alter your config.
"""

##
# Clare Sloggett, VLSCI, University of Melbourne
# Authored as part of the Genomics Virtual Laboratory project
##

import os
import IPython.lib
import logging
import subprocess
import stat
import argparse
import random
import string

profile_name = "nbserver"
ipython_port =  9510
ipython_location = "/ipython"

profile_config = \
"""
# Configuration file for ipython, intended for notebook server.
# Generated by GVL setup script.

c = get_config()

# plotting support by default
c.IPKernelApp.pylab = 'inline'

# rmagic extension by default
c.InteractiveShellApp.extensions = [
    'rmagic'
]

# Do not open local browser, just run as a server
c.NotebookApp.open_browser = False

# Require password authentication
c.NotebookApp.password = u'{hash}'

# Use a known port, which should match that in nginx port forwarding.
# Do not try any other ports.
# If you are editing your config to allow multiple instances of IPython Notebook
# to run simultaneously, you may want to change these settings.
c.NotebookApp.port = {port}
c.NotebookApp.port_retries = 0

# Assume that we will run at a subdirectory when port-forwarded
c.NotebookApp.base_project_url = '{location}/'
c.NotebookApp.base_kernel_url = '{location}/'
c.NotebookApp.webapp_settings = {{'static_url_prefix':'{location}/static/'}}

# Above, we do not set c.NotebookApp.ip, so by default Notebook will only
# listen on localhost. We are relying on NGINX port forwarding.
# We also do not set up encryption, as NGINX will do this for us.
# If you want to use open ports directly instead, we have created self-signed
# certificates for convenience. Comment out the subdirectory config above and uncomment
# the following lines:
#c.NotebookApp.ip = '*'
#c.NotebookApp.certfile = u'{certfile}'
#c.NotebookApp.keyfile = u'{keyfile}'
"""

extension_javascript = \
"""
require(["nbextensions/toc"], function (toc) {
    console.log('Table of Contents extension loaded');
    toc.load_ipython_extension();
});
"""

def main(system_password):
    """ The body of the script. """

    # Initialise logging to print info to screen
    logging.basicConfig(level=logging.INFO)

    # Get locations
    ipython_dir = IPython.utils.path.get_ipython_dir()

    # Create the nbserver profile
    logging.info("Creating ipython profile for "+profile_name)
    profile_dir = os.path.join(ipython_dir, "profile_"+profile_name)
    run_cmd("ipython profile create "+profile_name)

    # Ask the user for a password; only store the hash
    logging.info("Configuring password")
    if not system_password:
        print "\nEnter a password to use for ipython notebook web access."
        print "It is usually ok to use the same password as previously chosen for the linux account."
        password_hash = IPython.lib.passwd()
    else:
        password_hash = system_password_to_hash(system_password)

    # Generate a self-signed certificate
    logging.info("Generating self-signed certificate for SSL encryption")
    certfile = os.path.join(profile_dir, "user_selfsigned_cert.pem")
    keyfile = os.path.join(profile_dir, "user_selfsigned_key.pem")
    run_cmd("yes '' | openssl req -x509 -nodes -days 3650 -newkey rsa:1024 -keyout "+keyfile+" -out "+certfile)
    run_cmd("chmod 440 "+keyfile)

    # Install MathJax locally (into this profile)
    # Note that this import will fail if the default(?) profile isn't created beforehand
    from IPython.external.mathjax import install_mathjax
    mathjax_dest = os.path.join(profile_dir, 'static', 'mathjax' )
    install_mathjax(tag="v2.2-latest", dest=mathjax_dest)

    # Install the Table of Contents extension into this profile
    logging.info("Installing python notebook Table of Contents extension")
    extension_dir = os.path.join(ipython_dir, 'nbextensions')
    custom_dir = os.path.join(profile_dir, 'static', 'custom')
    run_cmd("mkdir -p "+extension_dir)
    run_cmd("curl -L https://rawgithub.com/minrk/ipython_extensions/master/nbextensions/toc.js > "+os.path.join(extension_dir,"toc.js"))
    run_cmd("curl -L https://rawgithub.com/minrk/ipython_extensions/master/nbextensions/toc.css > "+os.path.join(extension_dir,"toc.css"))
    run_cmd("mkdir -p "+custom_dir)
    with open(os.path.join(custom_dir, "custom.js"),"wb") as f:
        f.write(extension_javascript)

    # Overwrite the default profile config with ours
    config_file = os.path.join(profile_dir, "ipython_notebook_config.py")
    logging.info("Writing nbserver config file "+config_file)
    with open(config_file, 'wb') as f:
        f.write(profile_config.format(hash = password_hash,
                                      port = ipython_port,
                                      location = ipython_location,
                                      certfile = certfile,
                                      keyfile = keyfile))

def cmd_output(command):
    """Run a shell command and get the standard output, ignoring stderr."""
    return run_cmd(command)[0].strip()

def run_cmd(command):
    """ Run a shell command. """
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return process.communicate()

def system_password_to_hash(password):
    """Accepts a password in /etc/shadow format and returns the hashlib equivalent"""
    fragments = password.split(":")
        
    if fragments[1] == "1":
        algorithm = "md5"
    elif fragments[1] == "5":
        algorithm = "sha256"
    elif fragments[1] == "6":
        algorithm = "sha512"
    else:
        raise Exception("Unrecognised password format...")
    
    return "{0}:{1}:{2}".format(algorithm, fragments[2], fragments[3]) 

def id_generator(size=8, chars=string.ascii_uppercase + string.digits):
    """ Generates a random password """
    return ''.join(random.choice(chars) for _ in range(size))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--silent", action='store_true', default=False, help="Whether to run in silent install mode")
    parser.add_argument("-p", "--syspassword", default=None, help="System password from /etc/shadow. Used only in silent mode.")
    args = parser.parse_args()
    
    if args.silent and not args.syspassword:
        args.syspassword = id_generator()
    
    main(args.syspassword)
