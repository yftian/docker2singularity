import re
import inspect

class DockerFileToSingularityFile:
    FILE_TEMPLATE = """
Bootstrap: {bootstrap}
From: {image}

%setup
    # Commands to be run on the host system after the os has been copied
    # Has access to $SINGULARITY_ROOTFS to access the root filesystem
    # Acts like ordinary shell
    {setup}


%files
    # Files to be copied to the container before %post
    # Docker ADD, COPY
    # Must be in the format:
    #
    # filename1
    # filename2 /home/placetogo/
    #
    # filename1 will be placed into the root of the filesystem
    {files}


%labels
    # Metadata to add to the image
    # Must be in the format
    #
    # <key> <value>
    # VERSION 5
    {labels}


%post
    # commands to be executed inside container during bootstrap
    # Has access to %files and %setup, and maybe %labels via /.singularity.d/labels.json
    # Has access to $SINGULARITY_ENVIRONMENT to be able to set build time generated environment variables available at run time
    # For example:
    #
    # echo 'export JAWA_SEZ=wutini' >> $SINGULARITY_ENVIRONMENT
    {post}


%environment
    # Environmental variables to be added AT RUN TIME
    # These variables are not available in %post
    # This must be in the form of:
    #
    # FOO=BAR
    # ABC=123
    # export FOO ABC
    #
    {environment}


%runscript
    # commands to be executed when the container runs
    if [ -z "$1" ]
    then
        exec {entrypoint} {cmd}
    else
        exec {entrypoint} "$@"
    fi


%test
    # Singularity can run tests, put that here
    # Acts like a normal shell
    {test}

"""

    PARAM_ALLOWABLE_CHARACTERS_REGEX = '\w\ \t\\' + '\\'.join("!@#$%^&*()-_=+[{]}\|;:'\",<.>/?~`")
    PARAM_PATTERN = r'(?:[{PARAM_ALLOWABLE_CHARACTERS_REGEX}]+\s*\\\s*)*(?:[{PARAM_ALLOWABLE_CHARACTERS_REGEX}]+)\n'.format(
        PARAM_ALLOWABLE_CHARACTERS_REGEX=PARAM_ALLOWABLE_CHARACTERS_REGEX)
    SEARCH_PATTERN = r'^\s*(\w+)\s+({PARAM_PATTERN})'.format(PARAM_PATTERN=PARAM_PATTERN)

    def __init__(self, docker_image_name, folder='./'):
        self.clear_state()
        self.docker_image_name = docker_image_name  # Needed for pulling images from dockerhub
        self.folder = folder
        self.dockerfile_code = []

        self.ops = {}

        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            # Instructions are defined by being all uppercase
            if name.isupper():
                self.ops[name] = method

    def clear_state(self):
        self.bootstrap = ""
        self.image = ""
        self._setup = ""  # TODO do I need this?
        self.setup = ""
        self.files = ""
        self.labels = ""
        self.post = ""
        #self.environment = ""
        self._environment = {}
        self.entrypoint = ""
        self.cmd = ""
        self.test = ""
        self.docker_workdir = "/"

    def parse(self, code):
        self.dockerfile_code.append(code)

        # Remove all comment lines
        code = '\n'.join([line for line in code.split('\n') if not re.match(r'^\s*#', line)])
        # Need an empty line at the end
        if not code.endswith('\n'):
            code += '\n'

        for inst, params in re.findall(self.SEARCH_PATTERN, code, re.MULTILINE):
            # Remove any extra lines in params
            # XXX Need to find a better way to do this
            params = '\n'.join([line for line in params.split('\n') if line.split()]) + '\n'
            print('inst: `{inst}`; params: `{params}`'.format(inst=inst, params=params.strip()))
            self.post += '\n    # {inst} {params}'.format(inst=inst, params=params.replace('\\', '').replace('\'', '').replace('"', '')[:min([30, params.find('\n')]) if len(params) > 30 else len(params)].strip() + '...' if len(params) > 30 else '')
            op = self.ops[inst]
            op(params)

    def FROM(self, params):
        """
        FROM <image> [AS <name>]
        FROM <image>[:<tag>] [AS <name>]
        FROM <image>[@<digest>] [AS <name>]
        """
        # First we need to substitute variables in environment with the params
        if self.image:
            self.post += '    # skipped, already have image'.format(params=params)
            return
        for key in self._environment:
            # ${variable} format
            search_list = ['${key}'.format(key=key), '${{{key}}}'.format(key=key)]
            for s in search_list:
                if s in params:
                    # Do replacement
                    params = params.replace(s, self._environment[key])
                    continue

        # Encountering a new FROM clears all state
        self.clear_state()
        self.post += '\n    # FROM {params}'.format(params=params.strip())

        print('---FROM: ' + params)
        # Get everything in the form given in the docstring. Include characters, digits, and '-'
        regex = r"^(?:([\w\-\d\.]+)\/)?([\w\-\d\.]+)(?::([@:\w\-\d\.]+))?$"

        # Get the values, set default ones if need be
        m = re.match(regex, params)
        if not m:
            raise Exception("Malformed params for FROM: {params}".format(params=params.encode()))
        user, image, tag = m.groups()
        user = user + '/' if user else ''
        tag = tag if tag else 'latest'
        print(user, image, tag)

        self.bootstrap = 'docker'
        self.image = '{user}{image}:{tag}'.format(user=user, image=image, tag=tag)

    def MAINTAINER(self, params):
        """
        MAINTAINER <name>
        Deprecated and ignored
        """
        return

    def RUN(self, params):
        """
        RUN <command>
        RUN ["executable", "param1", "param2", ...]
        """
        if params.startswith('['):
            # RUN [...]
            try:
                s = self.get_list_string(params)
            except:
                raise Exception("Malformed params for RUN: {params}".format(params=params))
            self.post += '\n    ' + ' '.join(s)
        else:
            self.post += '\n    ' + params

    def ENV(self, params):
        """
        ENV <key> <value>
        ENV <key>=<value> ...
        """
        for key,value in self.get_key_value_pairs(params):
            # If we have some args then replace them when nessesary
            if value.startswith('$'):
                _tmpvalue = value.replace('$', '')
                if _tmpvalue in self._environment:
                    value = self._environment[_tmpvalue]
            self.post += '\n    echo \'export {key}={value}\' >> $SINGULARITY_ENVIRONMENT'.format(key=key, value=value)
            self.post += '\n    export {key}={value}'.format(key=key, value=value)

    def get_key_value_pairs(self, params):
        # Linearize it
        params = ' '.join((line.replace('\\', '').strip() for line in params.splitlines()))
        no_double_quotes = self.PARAM_ALLOWABLE_CHARACTERS_REGEX.replace('\"', '')
        regex = r'([\w\.\d]+)[=\s+]((?:[{no_double_quotes}]+)|(?:\"[{no_double_quotes}]+\"))'.format(no_double_quotes=no_double_quotes)
        regex = self.SEARCH_PATTERN.replace('\"', '')
        regex = r'([\w\.\d]+)[=\s+]?((?:[{no_double_quotes}]+)|(?:\"[{no_double_quotes}]+\"))?'.format(no_double_quotes=no_double_quotes)
        pairs = []
        while params:
            # Get one match, then do it again on the rest of the string
            m = re.match(regex, params)
            if not m:
                raise Exception("Malformed params: {params}".format(params=params.encode()))
            key, value = m.groups()
            pairs.append((key, value))
            params = params[m.span()[1]:].strip()
        return pairs

    def WORKDIR(self, params):
        """
        WORKDIR /path/to/workdir
        """
        self.workdir = params

    def singularity_file(self):
        """
        Return the formated Singularity file
        """
        return self.FILE_TEMPLATE.format(bootstrap=self.bootstrap,
                                         image=self.image,
                                         setup=self.setup,
                                         files=self.files,
                                         labels=self.labels,
                                         post=self.post,
                                         environment=self.environment,
                                         entrypoint=self.entrypoint,
                                         cmd=self.cmd,
                                         test=self.test)

    @property
    def environment(self):
        values = '\n    '.join(
            ["{key}={value}".format(key=key, value=value) for key, value in self._environment.items()])
        if values:
            return values + '\n    export ' + ' '.join([key for key in self._environment])
        else:
            return '\n'