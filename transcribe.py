#!/usr/bin/env python
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import argparse
import logging
import sys

import speech_recognition as s2t

from listen_loop import Assistant


DEFAULT_VOICE = 'Kate'  # System voice to use
DEFAULT_ALIAS = 'Panda'  # Wake word; see what is recognized easiest

SERVICES = (
    'Google',
    'GoogleCloud',
    'Sphinx',
    'Wit.ai',
    'Bing',
    'Houndify',
    'IBM',
    )
DEFAULT_SERVICE = SERVICES[0]

DEFAULT_DUTY = 2  # seconds to run between continuous loops
DEFAULT_LIMIT = 3  # seconds allotted to complete a phrase
DEFAULT_DURATION = 1  # seconds allotted to calibrate microphone
DEFAULT_TIMEOUT_WAKEWORD = 1  # seconds to give wake word in continuous mode
DEFAULT_TIMEOUT_COMMAND = 5  # seconds to give a command after wake word in
                             #   continuous mode
DEFAULT_SKILL_THRESHOLD = 3  # Number of times a command must be reinforced
DEFAULT_PHRASE = 'help me'

LOG_LEVELS = ('CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG')
DEFAULT_LOG_LEVEL = LOG_LEVELS[3]
LOGGER = logging.getLogger()


def parse_args():
    """Parse user arguments and return as parser object.

    Returns:
        Parser object with arguments as attributes.
    """
    parser = argparse.ArgumentParser(
        description='Simple Transcribe Assistant',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-f', '--file',
        help='Full path to the File to transcribe.')
    parser.add_argument(
        '-p', '--phrase',
        help='Phrase to speak; used primarily for testing purposes.')

    parser.add_argument(
        '-v', '--voice', default=DEFAULT_VOICE,
        help='System voice to use for speech.')
    parser.add_argument(
        '-a', '--alias', default=DEFAULT_ALIAS,
        help='An alias name for the system voice to use as wake word.')

    parser.add_argument(
        '-d', '--duty', default=DEFAULT_DUTY, type=int,
        help='Time, in seconds, to listen for phrases between loops.')
    parser.add_argument(
        '-l', '--limit', default=DEFAULT_LIMIT, type=int,
        help='Length, in seconds, of speech to parse.')
    parser.add_argument(
        '-m', '--duration', default=DEFAULT_DURATION, type=int,
        help='Length, in seconds, to listen for noise to calibrate the mic.')
    parser.add_argument(
        '-s', '--service', choices=SERVICES, default=DEFAULT_SERVICE,
        help='Which speech recognition service to use.')
    parser.add_argument(
        '-w', '--timeout_wakeword', default=DEFAULT_TIMEOUT_WAKEWORD,
        help='Length, in seconds, to wait for wake word in continuous mode.')
    parser.add_argument(
        '-t', '--timeout_command', default=DEFAULT_TIMEOUT_COMMAND,
        help='Length, in seconds, to wait for command after wake word in'
             ' continuous mode.')

    parser.add_argument(
        '-L', '--loglevel', choices=LOG_LEVELS, default=DEFAULT_LOG_LEVEL,
        help='Set the logging level.')
    args = parser.parse_args()
    return args


def main():
    """The main script.
    """
    assistant = Assistant(ARGS.voice, ARGS.alias, ARGS.service, ARGS.duty,
                          ARGS.limit, ARGS.duration, ARGS.timeout_wakeword,
                          ARGS.timeout_command)
    if ARGS.file:
        LOGGER.info('Reading file %s', ARGS.file)
        with s2t.AudioFile(ARGS.file) as source:
            audio = assistant.recognizer.record(source)  # read audio file
        LOGGER.info('Converting file %s', ARGS.file)
        output = assistant.audio_to_text(audio=audio)
    else:
        LOGGER.info('Listening:')
        output = assistant.listen()
    LOGGER.info('Transcription:\n%s', output)


if __name__ == '__main__':
    ARGS = parse_args()
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',
                        level=getattr(logging, ARGS.loglevel))
    sys.exit(main())
