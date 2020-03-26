import logging
import argparse
import datetime
import sys

import converter.image_types
import converter.parsers

logging.basicConfig(level=logging.DEBUG)

def get_single_dockerfile(image):
    if len(image.children) > 1:
        # TODO add functionality
        raise Exception("No way to handle diverging trees yet")
    return "### {name} --- {date}\n{current_dockerfile}\n{next}".format(name=image.name,
                                                                        date=str(datetime.datetime.now()),
                                                                        current_dockerfile=image.dockerfile,
                                                                        next=get_single_dockerfile(
                                                                            list(image.children.values())[
                                                                                0]) if image.children else '')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Create Dockerfile and singularity")
    parser.add_argument('-f', '--file', type=str, help="Where to write the file out to", default='singularity')
    parser.add_argument('--make-singularity', action='store_true', default='--make-singularity')
    parser.add_argument('--singularity-bootstrap', help="Sets the Bootstrap field of the Singularity definition file",
                        default='docker')
    parser.add_argument('--singularity-from',
                        help="Sets the From field of the Singularity definition file; Default is to use the root image from docker")
    parser.add_argument('image_name', type=str, help="The name of the Docker image, as such: 'jupyterhub/jupyterhub'")
    args = parser.parse_args()

    root = converter.image_types.DockerImage.get_tree(args.image_name)
    docker_file = get_single_dockerfile(root)

    file_prefix = "# Created with `{argv}`\n".format(argv=' '.join(sys.argv))
    if args.make_singularity:
        bootstrap = args.singularity_bootstrap
        _from = args.singularity_from or root.name
        print(bootstrap, _from)

        parser = converter.parsers.DockerFileToSingularityFile(args.image_name, folder='./')
        parser.parse(docker_file)
        parser.bootstrap = bootstrap
        parser.image = _from
        with open(args.file, 'w') as f:
            f.write(file_prefix + parser.singularity_file())
        with open('Dockerfile', 'w') as f:
            f.write(file_prefix + docker_file)
    else:
        with open(args.file, 'w') as f:
            f.write(docker_file)
