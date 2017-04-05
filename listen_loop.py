#!/usr/bin/env python
"""Simple demo that listens for speech, then processes it.

See: https://pypi.python.org/pypi/SpeechRecognition/

Requirements:
1. REQUIRES MacOS as it uses the system voice to read text.
2. Python SpeechRecognition module, which in turn requires:
    a. $ brew install portaudio && brew link portaudio
    b. $ sudo -H pip install pyaudio
    c. Google Speech Recognition, but should be updated to use Sphinx.

To do:
1. Allow augmentation of skills through files (YAML? JSON?)
2. Tighten continuous listening ability.
3. Integrate Sphinx.
4. De-uglify

In continuous mode, the loop gets stuck occasionally.  It is possible
that I should wait some time for the listener to stop before starting
the next loop, but that creates more "dead" air time, doesn't it?
That's a question.

Ideas for projects:
 1. Listen for phrases that are not programmed.
    Compare words in those phrases with skill names and command words.
    Even if you don't know, use the skill that correlates highest.
    Get feedback on the guessed skills (were they expected? No?)
    Give the unknown phrases a ranking based on the feedback.
    As confidence grows higher, add the phrases to skill command lists.
    = Learning new synonyms for skill commands.
 2. For phrases that are not skills (rank low), forward those to Google.
    Store the responses tied to the phrases.
    On the next occurrence of unknown phrases, give the stored answers.
    Get feedback on the guessed answers (were they expected? No?)
    Give answers and unknown phrases rankings based on the feedback.
    As confidence in answers grow, add the answers to phrase responses.
    As confidence in phrases grow, add the phrases to new command lists.
    Find common words in the phrases and answers and create skill names.
    Create skills based on the type of phrases and answers.
    Add the command lists and responses to the new skills.
    = Learning new skills.
"""

import argparse
import logging
import random
import sys
import time

from os import system

import speech_recognition as s2t


DEFAULT_VOICE = 'Ava'  # System voice to use
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

DEFAULT_DUTY = 5  # seconds to run between continuous loops
DEFAULT_LIMIT = None  # seconds allotted to complete a phrase
DEFAULT_DURATION = 2  # seconds allotted to calibrate microphone

DEFAULT_PHRASE = 'help me'

SKILLS = {
    'help': {
        'commands': (
            'help me',  # More precise or encapsulating should come first
            'help',
            ),
        },
    'date': {
        'commands': (
            'date',
            'what date is it',
            "what's the date",
            'what is the date',
            'what day is it',
            ),
        'pattern': 'Today is %A %d %B %Y',
        },
    'time': {
        'commands': (
            'time',
            'what time is it',
            "what's the time",
            'what is the time',
            ),
        'pattern': 'It is now %H:%M',
        },
    'joke': {
        'commands': (
            'joke',
            'tell me a joke',
            ),
        'random': (
            "Knock knock. Who's there? Amish. Amish who? You're not a shoe!",
            ),
        },
    'riddle': {
        'commands': (
            'riddle',
            'tell me a riddle',
            'ask me a riddle',
            ),
        'random': (
            "What's long, brown, and sticky? ... A stick!",
            "What's orange and sounds like a parrot? ... A carrot!",
            ),
        },
    'turn on': {
        'commands': (
            'turn on',
            'enable',
            ),
        },
    'turn off': {
        'commands': (
            'turn off',
            'disable',
            ),
        'response': 'There is currently nothing on to turn off.',
        },
    'greeting': {
        'commands': (
            'hello',
            'hi',
            'good morning',
            'good day',
            'good evening',
            ),
        'response': 'Hello yourself!',
        },
    'farewell': {
        'commands': (
            'goodbye',
            'bye',
            'goodnight',
            'good night',
            'sayonara',
            ),
        'response': 'But we are just getting started!',
        },
    'quit': {
        'commands': (
            'stop listening',
            ),
        },
    'identity': {
        'commands': (
            'who are you',
            'where did you come from',
            'who made you',
            'how old are you',
            ),
        'response': 'My real name is %s and I was created by Kevin in'
                    ' April 2017.' % DEFAULT_ALIAS,
        },
    }

LOG_LEVELS = ('CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG')
DEFAULT_LOG_LEVEL = LOG_LEVELS[3]
LOGGER = logging.getLogger()


class Assistant(object):
    """Omnipresent Assistant object..."""
    def __init__(self, voice=DEFAULT_VOICE, alias=DEFAULT_ALIAS,
                 service=DEFAULT_SERVICE, duty=DEFAULT_DUTY,
                 limit=DEFAULT_LIMIT, duration=DEFAULT_DURATION):
        """Initialiaze...

        Args:
            voice: System voice to use.
            alias: Assistant name, to use as the wake word.
            service: Speech Recognition service to use.
            duty: Time, in seconds, between listening loops.
            limit: Time, in seconds, to wait for phrases.
            duration: Time, in seconds, to calibrate microphone.
        """
        self.__exit_loop = False
        self.voice = voice
        self.alias = alias
        self.service = service
        self.duty = duty
        self.limit = limit
        self.duration = duration

        self.__skills = SKILLS  # This will be augmented later...

        self.recognizer = s2t.Recognizer()
        self.microphone = s2t.Microphone()
        # Calibrate the microphone once before we start listening:
        self.calibrate_mic()
        LOGGER.info("Your assistant's name is %s.", self.alias)

    def calibrate_mic(self, duration=None):
        """Calibrate the microphone against background noises.

        Args:
            duration: Optional time, in seconds, to listen for noise.
        """
        LOGGER.debug('calibrate_mic: Calibrating microphone.')
        duration = duration or self.duration
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=duration)
        LOGGER.debug('calibrate_mic: Microphone calibrated.')

    def listen(self, timeout=None, limit=None):
        """Listen for a spoken phrase and return as text.

        Args:
            timeout: Time, in seconds, to wait for speech.  The default
                is no time limit (None).
            limit: UNUSED.  Time, in seconds, to wait for phrase.
                If not provided, object default will be used.

        Returns:
            phrase: Text representation of speech, or None.
        """
        self.speak('Listening')
        # Need a new microphone as source as listen_in_background()
        #   already uses the object's microphone inside a context manager...
        with s2t.Microphone() as source:
            audio = self.recognizer.listen(source, timeout=timeout)
        phrase = self.audio_to_text(audio=audio, continuous=False)
        return phrase

    def listen_loop(self, duty=None, limit=None):
        """Listen continuously in a loop until told to stop.

        Args:
            duty: Time, in seconds, between listening loops.
                If not provided, object default will be used.
            limit: Time, in seconds, to wait for phrase.
                If not provided, object default will be used.
        """
        duty = duty or self.duty
        cycle = 0.1
        divisions = int(duty / cycle)
        limit = limit or self.limit

        self.speak('Listening')
        while not self.__exit_loop:
            LOGGER.info('%s is waiting in continuous mode...', self.alias)
            stop_listening = self.recognizer.listen_in_background(
                self.microphone, self.audio_to_text,
                phrase_time_limit=limit)
            for _ in range(divisions):
                time.sleep(cycle)
            stop_listening()
        # __exit_loop is set in audio_to_text, and reset here:
        self.__exit_loop = False

    def audio_to_text(self, recognizer=None, audio=None,
                      service=None, continuous=True):
        """Convert audio to text via a Speech Recognition service.

        The ordering of the first two arguments is due to this method
        being used as a callback to listen_in_background().  As a class
        instance method, only audio is required.

        Args:
            recognizer: Speech Recognizer instance (required for callback)
            audio: Audio data from a listener.
            service: Speech Recognition service to use.
            continuous: Boolean; if True, processes the converted text
                before returning.  The default is True as the background
                listener cannot send arguments to the callback function.

        Returns:
            phrase: Text representation of speech, or None.
        """
        recognizer = recognizer or self.recognizer
        service = service or self.service
        try:
            if service == 'Google':
                phrase = recognizer.recognize_google(audio)
            else:
                phrase = 'The %s Recognizer is not yet implemented' % service
            LOGGER.info('audio_to_text: %s heard: %s', service, phrase)
        except s2t.UnknownValueError:
            LOGGER.error('audio_to_text: %s could not parse audio', service)
            phrase = None
        except s2t.RequestError as exc:
            LOGGER.error('audio_to_text: %s did not respond; %s', service, exc)
            phrase = None
        if phrase and continuous:
            phrase = self.process_phrase(phrase, require_wake_word=True)
        return phrase

    def process_phrase(self, phrase, require_wake_word=False):
        """Process a raw phrase (may include wake word).

        Args:
            phrase: Text to process.
            require_wake_word: Boolean; if True, requires wake word in
                order to process commands within the phrase.

        Returns:
            response: Processed text phrase, or None.
        """
        if starts_with(phrase, self.alias):
            # If there is a command, extract it by removing wake word:
            phrase = remove_leading_words(phrase, self.alias)
            # If wake word only, give the user a chance to give a command:
            #   But is this really a good idea?
            if not phrase:
                phrase = self.listen()
        else:
            if require_wake_word:
                LOGGER.warning('process_phrase: Required wake word not found.')
                phrase = 'Wake word was not found, but I heard "%s"' % phrase
                phrase = None
        # The phrase should be a command at this point (no wake word):
        if phrase:
            response = self.process_command(phrase)
            self.speak(response)
        else:
            response = None
        return response

    def process_command(self, phrase):
        """Processes a command phrase.

        Args:
            phrase: Text containing command to execute, but no wake word.

        Returns:
            response: Text response for feedback.
        """
        if phrase:
            response = None
            for skill in self.__skills:
                for command in self.__skills[skill]['commands']:
                    operand = remove_leading_words(phrase, command)
                    if operand != phrase:
                        LOGGER.debug('process_command: command = %s (%s)',
                                     command, operand)
                        response = self.do_skill(skill, operand)
                        break
                if response:
                    break
            if not response:
                response = 'I do not know how to %s' % phrase
        else:
            response = 'I do not understand what you are trying to tell me!'
        return response

    def do_skill(self, skill, operand):
        """Simplifying skill operations...

        Args:
            skill: Name of skill (skill section name in SKILLS)
            operand: Remainder of phrase, without wake word or commands.

        Returns:
            response: Text response to the skill/command invocation.
        """
        resources = self.__skills[skill]
        if 'response' in resources:
            # Some responses are fixed:
            response = resources['response']
        elif 'random' in resources:
            # Some have a variety of fixed responses:
            response = random.choice(resources['random'])
        elif skill == 'help':
            if operand and operand in self.__skills:
                resp_parts = (
                    'These commands are available for the %s skill' % operand,
                    ) + self.__skills[operand]['commands']
                response = ': ... '.join(resp_parts)
            else:
                resp_parts = [
                    'To list commands for a specific skill, simply say "help"'
                    ' followed by the name of the skill.  The following skills'
                    ' are currently supported',
                    ] + sorted([skill_name for skill_name in self.__skills])
                response = ': ... '.join(resp_parts)
        elif skill == 'date':
            localtime = time.localtime(time.time())
            response = time.strftime(resources['pattern'], localtime)
        elif skill == 'time':
            localtime = time.localtime(time.time())
            response = time.strftime('It is now %H:%M', localtime)
        elif skill == 'quit':
            response = 'Stopping now'
            # This controls the listen_loop():
            self.__exit_loop = True
        elif skill == 'turn on':
            if operand:
                response = 'I cannot turn on %s' % operand
            else:
                response = 'You need to tell me what to turn on'
        else:
            response = 'I am not yet programmed for the skill %s' % skill
        return response

    def speak(self, phrase):
        """Simple speech wrapper.

        Args:
            phrase: Text to speak.
        """
        if phrase:
            LOGGER.info('%s says: %s', self.alias, phrase)
            system('say -v %s "%s"' % (self.voice, phrase))
        else:
            LOGGER.debug('speak: (%s ignored "%s")', self.alias, phrase)


def remove_leading_words(phrase, leader):
    """Removes leading whole words from a phrase.

    Useful for removing wake words or commands, perhaps?

    Args:
        phrase: Text to check.
        leader: Text to be removed from front of phrase.

    Returns:
        Phrase with leading words removed, or the original phrase if
        there were no leading words to be removed.
    """
    phrase_parts = phrase.split()
    leader_len = len(leader.split())
    phrase_start = ' '.join(phrase_parts[:leader_len])
    if leader.lower() == phrase_start.lower():
        phrase = ' '.join(phrase_parts[leader_len:])
    LOGGER.debug('remove_leading_words: %s => %s', leader, phrase)
    return phrase


def starts_with(phrase, leader):
    """Detects the presence of leading word(s) in a phrase.

    Args:
        phrase: Text to check.
        leader: Text to check for in front of phrase.

    Returns:
        Boolean: True if leader starts the phrase, False otherwise.
    """
    new_phrase = remove_leading_words(phrase, leader)
    result = phrase != new_phrase
    return result


def parse_args():
    """Parse user arguments and return as parser object.

    Returns:
        Parser object with arguments as attributes.
    """
    parser = argparse.ArgumentParser(
        description='Simple Assistant',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-c', '--continuous', action='store_true',
        help='Switch mode to listen continuously in the background.')

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
        '-L', '--loglevel', choices=LOG_LEVELS, default=DEFAULT_LOG_LEVEL,
        help='Set the logging level.')
    args = parser.parse_args()
    return args


def main():
    """The main script.
    """
    assistant = Assistant(ARGS.voice, ARGS.alias, ARGS.service, ARGS.duty,
                          ARGS.limit, ARGS.duration)
    if ARGS.continuous:
        assistant.listen_loop()
    else:
        phrase = ARGS.phrase or assistant.listen() or DEFAULT_PHRASE
        assistant.process_phrase(phrase)


if __name__ == '__main__':
    ARGS = parse_args()
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',
                        level=getattr(logging, ARGS.loglevel))
    sys.exit(main())
