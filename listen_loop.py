#!/usr/bin/env python
"""Simple demo that listens for speech, then processes it.

See: https://pypi.python.org/pypi/SpeechRecognition/
     https://brew.sh/

Requirements:
1. REQUIRES MacOS as it uses the system voice to read text.
2. Python SpeechRecognition module, which in turn requires:
    @. sudo -H pip install SpeechRecognition
    a. $ brew install portaudio && brew link portaudio
    b. $ sudo -H pip install pyaudio
    c. Google Speech Recognition, but should be updated to use Sphinx.

To do:
1. Integrate Sphinx.
2. Tighten listening loop.  Sometimes gets stuck listening for wake word.
   Perhaps get the background listener working again...
3. Fix all parameter/argument inconsistencies and documentation.
4. De-uglify

In continuous mode, the loop gets stuck occasionally.  It is possible
that I should wait some time for the listener to stop before starting
the next loop, but that creates more "dead" air time, doesn't it?
That's a question.

Ideas for projects:
 1. For phrases that are not skills (rank low), forward those to Google.
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
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import argparse
import logging
import random
import json
import os
import sys
import time
import urllib

import speech_recognition as s2t


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

DDG_TEMPLATE = 'https://duckduckgo.com/html/?q=%s'

DEFAULT_SKILLS_FILE = 'default_skills.json'
MODIFIED_SKILLS_FILE = 'skills.json'

LOG_LEVELS = ('CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG')
DEFAULT_LOG_LEVEL = LOG_LEVELS[3]
LOGGER = logging.getLogger()


class Assistant(object):
    """Omnipresent Assistant object..."""
    def __init__(self, voice=DEFAULT_VOICE, alias=DEFAULT_ALIAS,
                 service=DEFAULT_SERVICE, duty=DEFAULT_DUTY,
                 limit=DEFAULT_LIMIT, duration=DEFAULT_DURATION,
                 timeout_wakeword=DEFAULT_TIMEOUT_WAKEWORD,
                 timeout_command=DEFAULT_TIMEOUT_COMMAND,
                 threshold=DEFAULT_SKILL_THRESHOLD):
        """Initialiaze...

        Args:
            voice: System voice to use.
            alias: Assistant name, to use as the wake word.
            service: Speech Recognition service to use.
            duty: Time, in seconds, between listening loops.
            limit: Time, in seconds, to wait for phrases.
            duration: Time, in seconds, to calibrate microphone.
            timeout: Time, in seconds, to give a command after wake word.
            threshold: Number of times a new command must be reinforced.
        """
        self.__exit_loop = False

        self.voice = voice
        self.alias = alias
        self.service = service
        self.duty = duty
        self.limit = limit
        self.duration = duration
        self.timeout_wakeword = timeout_wakeword
        self.timeout_command = timeout_command

        self.load_skills()
        self.threshold = threshold

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
        with self.microphone as source:
            try:
                audio = self.recognizer.listen(source, timeout=timeout,
                                               phrase_time_limit=limit)
                phrase = self.audio_to_text(audio=audio)
            except s2t.WaitTimeoutError:
                phrase = None
        return phrase

    def listen_background(self, duty=None, limit=None):
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

    def listen_loop(self):
        """Listen continuously in a loop until told to stop.

        Listens first for the wake word (alias), then for a command.
        """
        while not self.__exit_loop:
            LOGGER.info('listen_loop: Waiting for wake word (%s)', self.alias)
            phrase = self.listen(timeout=self.timeout_wakeword)
            if phrase == self.alias.lower():
                self.calibrate_mic()
                self.speak('Listening')
                phrase = self.listen(timeout=self.timeout_command)
                self.process_phrase(phrase)

    def audio_to_text(self, recognizer=None, audio=None, service=None):
        """Convert audio to text via a Speech Recognition service.

        The ordering of the first two arguments is due to this method
        being used as a callback to listen_in_background().  As a class
        instance method, only audio is required.

        Args:
            recognizer: Speech Recognizer instance (required for callback)
            audio: Audio data from a listener.
            service: Speech Recognition service to use.

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
        else:
            if require_wake_word:
                LOGGER.warning('process_phrase: Required wake word not found.')
                phrase = 'Wake word was not found, but I heard "%s"' % phrase
                phrase = None
        # The phrase should be a command at this point (no wake word):
        if phrase:
            response = self.process_command(phrase)
            if not response:
                self.speak('I do not know how to process %s' % phrase)
                self.speak('Here is what the internet thinks:')
                query_web(phrase)
            else:
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
                for command in [skill] + self.__skills[skill]['commands']:
                    operand = remove_leading_words(phrase, command)
                    if operand != phrase:
                        LOGGER.debug('process_command: command = %s (%s)',
                                     command, operand)
                        response = self.do_skill(skill, operand)
                        break
                if response:
                    break
            if not response:
                response = self.learn_command(phrase)
        else:
            response = 'I do not understand what you are trying to tell me!'
        return response

    def learn_command(self, phrase):
        """Learns a new command if the command contains a skill name.

        Args:
            phrase: phrase to process for a skill.

        Returns:
            Response phrase.
        """
        response = None
        for skill in self.__skills:
            LOGGER.debug('learn_command: Skill %s in "%s"?', skill, phrase)
            if skill in phrase:
                self.speak('Do you mean to use the skill %s?' % skill)
                response = self.listen()
                if response in ('yes', 'yup', 'yeah', 'affirmative'):
                    self.increase_command_candidate(skill, phrase)
                    response = self.process_command(skill)
                    break
                else:
                    self.decrease_command_candidate(skill, phrase)
                    response = None
        if not response:
            response = self.generalize_command(phrase)
        return response

    def generalize_command(self, phrase):
        """Add to or learn skills for a given command.

        Args:
            phrase: phrase to process for a skill.

        Returns:
            Response phrase.
        """
        self.speak('I do not know which skill you want to use.')
        for skill in sorted(self.__skills):
            LOGGER.debug('learn_skill: Skill %s in "%s"?', skill, phrase)
            self.speak('Do you mean to use the skill %s?' % skill)
            response = self.listen()
            if response in ('skip', 'stop'):
                response = None
                break
            elif response in ('yes', 'yup', 'yeah', 'affirmative'):
                self.increase_command_candidate(skill, phrase)
                response = self.process_command(skill)
                break
            else:
                self.decrease_command_candidate(skill, phrase)
                response = None
        if not response:
            response = self.learn_skill(phrase)
        return response

    def learn_skill(self, command):
        """Potentially learn a new skill for a given command.

        This only learn simple response skills currently.

        puts skill into candidate skill structure
        puts command into candidate command structure under candidate skill.
        learn candidate response.
            what is the response you want?
            Is this the response you expect?
        On threshold response (command and skill will always be <= response,
            move candidate response to response
            move candidate command to command
            move candidate skill to skill
        on 0
            remove candidate skill structure...
        """
        pass

    def increase_command_candidate(self, skill, command):
        """Increase the likelihood of a command candidate for a skill.

        Args:
            skill: Name of a skill to modify.
            command: The command phrase.
        """
        if command in self.__skills[skill]['candidates']:
            self.__skills[skill]['candidates'][command] += 1
            if self.__skills[skill]['candidates'][command] >= self.threshold:
                self.__skills[skill]['commands'].append(command)
                del self.__skills[skill]['candidates'][command]
                self.speak('I have learned the command %s for the skill %s'
                           % (command, skill))
        else:
            self.__skills[skill]['candidates'][command] = 1
        if command in self.__skills[skill]['candidates']:
            LOGGER.debug('increase_command_candidate: Candidate "%s": %s',
                         command, self.__skills[skill]['candidates'][command])

    def decrease_command_candidate(self, skill, command):
        """Decrease the likelihood of a command candidate for a skill.

        Args:
            skill: Name of a skill to add command.
            command: The command phrase to add.
        """
        if command in self.__skills[skill]['candidates']:
            self.__skills[skill]['candidates'][command] -= 1
            LOGGER.debug('decrease_command_candidate: Candidate "%s": %s',
                         command, self.__skills[skill]['candidates'][command])
            if self.__skills[skill]['candidates'][command] < 0:
                del self.__skills[skill]['candidates'][command]
                self.speak('I have forgotten the command %s for the skill %s'
                           % (command, skill))
        if command in self.__skills[skill]['candidates']:
            LOGGER.debug('decrease_command_candidate: Candidate "%s": %s',
                         command, self.__skills[skill]['candidates'][command])

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
                resp_parts = [
                    'These commands are available for the "%s" skill' % operand
                    ] + self.__skills[operand]['commands']
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
            os.system('say -v %s "%s"' % (self.voice, phrase))
        else:
            LOGGER.debug('speak: (%s ignored "%s")', self.alias, phrase)

    def load_skills(self):
        """Load skills from a file.

        Returns:
            Skills dictionary.
        """
        for filename in (MODIFIED_SKILLS_FILE, DEFAULT_SKILLS_FILE):
            skills = load_json_file(filename)
            if skills:
                break
        self.__skills = skills

    def save_skills(self):
        """Save modified skills file.
        """
        jsonized = json.dumps(self.__skills, indent=4, sort_keys=True)
        save_json_file(jsonized, MODIFIED_SKILLS_FILE)


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
    if phrase:
        phrase_parts = phrase.split()
        leader_len = len(leader.split())
        phrase_start = ' '.join(phrase_parts[:leader_len])
        if leader.lower() == phrase_start.lower():
            phrase = ' '.join(phrase_parts[leader_len:])
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


def query_web(query):
    """Get query results from the web.

    Args:
        query: A search query to send to a search engine.

    Returns:
        A list of response data.
    """
    encoded = urllib.urlencode({'q': query})
    url = DDG_TEMPLATE % encoded
    resultstream = urllib.urlopen(url)
    results = resultstream.read()
    print(results)
    return results


def load_json_file(filename):
    """Load JSON string from a file.

    Args:
        filename: Name of the file containing JSON to load.

    Returns:
        File contents as Python dictionary, or None if file does not
        exist.
    """
    if os.path.isfile(filename):
        with open(filename, 'r') as filehandle:
            json_contents = filehandle.read()
        pythonized = json.loads(json_contents)
    else:
        pythonized = None
    return pythonized


def save_json_file(json_string, filename):
    """Save JSON string to a file.

    Args:
        json_string: JSON string to save.
        filename: Name of the file to save.
    """
    with open(filename, 'w') as filehandle:
        filehandle.write(json_string)


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
    assistant.speak('Starting')
    if ARGS.continuous:
        assistant.listen_loop()
        assistant.save_skills()
    else:
        phrase = ARGS.phrase or assistant.listen() or DEFAULT_PHRASE
        assistant.process_phrase(phrase)


if __name__ == '__main__':
    ARGS = parse_args()
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',
                        level=getattr(logging, ARGS.loglevel))
    sys.exit(main())
