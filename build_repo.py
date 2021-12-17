#!/usr/bin/env/ python3
# coding=utf-8
'''
Parse extensions/*.yaml files & build a directory with following structure:
public/
    |-my-extension-1/
    |   |-1.0.0/          <- version (to avoid static file caching issues)
    |   |   |-index.json  <- extension info
    |   |   |-index.html  <- extension entrance (component)
    |   |   |-dist        <- extension resources
    |   |   |-...         <- other files
    |-index.json          <- repo info, contain all extensions' info
'''
from subprocess import run, PIPE
import sys
import os
import json
import shutil
from zipfile import ZipFile
import requests
import yaml


def process_zipball(repo_dir, release_version):
    """
    Grab the release zipball and extract it without the root/parent/top directory
    """
    with ZipFile(os.path.join(repo_dir, release_version) + ".zip",
                 'r') as zipball:
        for member in zipball.namelist():
            # Parse files list excluding the top/parent/root directory
            filename = '/'.join(member.split('/')[1:])
            # Now ignore it
            if filename == '': continue
            # Ignore dot files
            if filename.startswith('.'): continue
            source = zipball.open(member)
            try:
                target = open(
                    os.path.join(repo_dir, release_version, filename), "wb")
                with source, target:
                    target = open(
                        os.path.join(repo_dir, release_version, filename),
                        "wb")
                    shutil.copyfileobj(source, target)
            except (FileNotFoundError, IsADirectoryError):
                # Create the directory
                os.makedirs(
                    os.path.dirname(
                        os.path.join(repo_dir, release_version, filename)))
                continue
    # Delete the archive zip
    os.remove(os.path.join(repo_dir, release_version) + ".zip")


def git_clone_method(ext_yaml, public_dir, ext_has_update):
    """
    Get the latest repository and parse for metadata
    """
    repo_name = ext_yaml['github'].split('/')[-1]
    repo_dir = os.path.join(public_dir, repo_name)
    run([
        'git', 'clone', 'https://github.com/{github}.git'.format(**ext_yaml),
        '--quiet', '{}_tmp'.format(repo_name)
    ],
        check=True)
    ext_last_commit = (run([
        'git', '--git-dir=' +
        os.path.join(public_dir, '{}_tmp'.format(repo_name), '.git'),
        'rev-list', '--tags', '--max-count=1'
    ],
                           stdout=PIPE,
                           check=True).stdout.decode('utf-8').replace(
                               "\n", ""))
    ext_version = run([
        'git', '--git-dir',
        os.path.join(public_dir, '{}_tmp'.format(repo_name), '.git'),
        'describe', '--tags', ext_last_commit
    ],
                      stdout=PIPE,
                      check=True).stdout.decode('utf-8').replace("\n", "")

    # check if the latest version already exist
    if not os.path.exists(os.path.join(repo_dir, ext_version)):
        ext_has_update = True
        shutil.move(
            os.path.join(public_dir, '{}_tmp'.format(repo_name)),
            os.path.join(public_dir, repo_name, '{}'.format(ext_version)))
        # Delete .git resource from the directory
        shutil.rmtree(
            os.path.join(public_dir, repo_name, '{}'.format(ext_version),
                         '.git'))
    else:
        # ext already up-to-date
        # print('Extension: {} - {} (already up-to-date)'.format(ext_yaml['name'], ext_version))
        # clean-up
        shutil.rmtree(os.path.join(public_dir, '{}_tmp'.format(repo_name)))
    return ext_version, ext_has_update


def parse_extensions(base_dir, base_url, ghub_session):
    """
    Build Standard Notes extensions repository using Github meta-data
    """

    extension_dir = os.path.join(base_dir, 'extensions')
    public_dir = os.path.join(base_dir, 'public')
    if not os.path.exists(os.path.join(public_dir)):
        os.makedirs(public_dir)
    os.chdir(public_dir)

    extensions = []
    # Get all extensions, sort extensions alphabetically along by their by type
    extfiles = [x for x in sorted(os.listdir(extension_dir)) if not x.endswith('theme.yaml') and x.endswith('.yaml')]
    themefiles = [x for x in sorted(os.listdir(extension_dir)) if x.endswith('theme.yaml')]
    extfiles.extend(themefiles)

    for extfile in extfiles:
        with open(os.path.join(extension_dir, extfile)) as extyaml:
            ext_yaml = yaml.load(extyaml, Loader=yaml.FullLoader)
        ext_has_update = False
        repo_name = ext_yaml['github'].split('/')[-1]
        repo_dir = os.path.join(public_dir, repo_name)

        # If we don't have a Github API Session, do git-clone instead
        if ghub_session is not None:
            # Get extension's github release meta-data
            ext_git_info = json.loads(
                ghub_session.get(
                    'https://api.github.com/repos/{github}/releases/latest'.
                    format(**ext_yaml)).text)
            try:
                ext_version = ext_git_info['tag_name']
            except KeyError:
                # No release's found
                print(
                    "Error: Unable to update %s (%s) does it have a release at Github?"
                    % (ext_yaml['name'], extfile))
                continue
            # Check if extension directory already exists
            if not os.path.exists(repo_dir):
                os.makedirs(repo_dir)
            # Check if extension with current release already exists
            if not os.path.exists(os.path.join(repo_dir, ext_version)):
                ext_has_update = True
                os.makedirs(os.path.join(repo_dir, ext_version))
                # Grab the release and then unpack it
                with requests.get(ext_git_info['zipball_url'],
                                  stream=True) as zipball_stream:
                    with open(
                            os.path.join(repo_dir, ext_version) + ".zip",
                            'wb') as zipball_file:
                        shutil.copyfileobj(zipball_stream.raw, zipball_file)
                # unpack the zipball
                process_zipball(repo_dir, ext_version)
        else:
            ext_version, ext_has_update = git_clone_method(
                ext_yaml, public_dir, ext_has_update)

        # Build extension info (stateless)
        # https://domain.com/sub-domain/my-extension/index.json
        extension = dict(
            identifier=ext_yaml['id'],
            name=ext_yaml['name'],
            content_type=ext_yaml['content_type'],
            area=ext_yaml.get('area', None),
            version=ext_version,
            description=ext_yaml.get('description', None),
            marketing_url=ext_yaml.get('marketing_url', None),
            thumbnail_url=ext_yaml.get('thumbnail_url', None),
            valid_until='2030-05-16T18:35:33.000Z',
            url='/'.join([base_url, repo_name, ext_version, ext_yaml['main']]),
            download_url='https://github.com/{}/archive/{}.zip'.format(
                ext_yaml['github'], ext_version),
            latest_url='/'.join([base_url, repo_name, 'index.json']),
            flags=ext_yaml.get('flags', []),
            dock_icon=ext_yaml.get('dock_icon', {}),
            layerable=ext_yaml.get('layerable', None),
            statusBar=ext_yaml.get('statusBar', None),
        )

        # Strip empty values
        extension = {k: v for k, v in extension.items() if v}

        # Check if extension is already up-to-date ()
        if ext_has_update:
            # Generate JSON file for each extension
            with open(os.path.join(public_dir, repo_name, 'index.json'),
                      'w') as ext_json:
                json.dump(extension, ext_json, indent=4)
            if extfile.endswith("theme.yaml"):
                print('Theme: {:34s} {:6s}\t(updated)'.format(
                    ext_yaml['name'], ext_version))
            else:
                print('Extension: {:30s} {:6s}\t(updated)'.format(
                    ext_yaml['name'], ext_version))
        else:
            # ext already up-to-date
            if extfile.endswith("theme.yaml"):
                print('Theme: {:34s} {:6s}\t(already up-to-date)'.format(
                    ext_yaml['name'], ext_version))
            else:
                print('Extension: {:30s} {:6s}\t(already up-to-date)'.format(
                    ext_yaml['name'], ext_version))

        extensions.append(extension)
    os.chdir('..')

    # Generate the main repository index JSON
    # https://domain.com/sub-domain/my-index.json
    with open(os.path.join(public_dir, 'index.json'), 'w') as ext_json:
        json.dump(
            dict(
                content_type='SN|Repo',
                valid_until='2030-05-16T18:35:33.000Z',
                packages=extensions,
            ),
            ext_json,
            indent=4,
        )
    print("\nProcessed: {:20s}{} extensions. (Components: {}, Themes: {})".format("", len(extfiles), len(extfiles)-len(themefiles), len(themefiles)))
    print("Repository Endpoint URL: {:6s}{}/index.json".format("", base_url))

def main(base_url):
    """
    teh main function
    """
    while base_url.endswith('/'):
        base_url = base_url[:-1]
        
    base_dir = os.path.dirname(os.path.abspath(__file__))




if __name__ == '__main__':
     main(os.getenv('URL', 'https://snext.netlify.app/'))
