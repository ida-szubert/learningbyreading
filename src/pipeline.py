#!/usr/bin/env python
from optparse import OptionParser
from disambiguation import disambiguation
from candc import tokenize, get_all, get_fol
import simplejson as json
import logging as log
from os import listdir
from os.path import isfile, join, dirname
from itertools import product, combinations
from collections import Counter
from mappings import bn2offset
import ConfigParser
from frameinstance import *
from lxml import objectify

# log configuration
log.basicConfig(level=log.INFO, format='%(asctime)s.%(msecs)03d %(levelname)s %(message)s')

# read configuration
config = ConfigParser.ConfigParser()
config.read(join(dirname(__file__),'../config/namespace.conf'))

with open(join(dirname(__file__),'../resources/thematic_roles.txt')) as f:
    thematic_roles = [line.rstrip() for line in f]
# command line argument partsing
parser = OptionParser()
parser.add_option('-i',
                  '--input',
                  dest="input_file",
                  help="read text from FILE",
                  metavar="FILE")
parser.add_option('-d',
                  '--input-dir',
                  dest="input_dir",
                  help="read text files from DIRECTORY",
                  metavar="DIRECTORY")
parser.add_option('-o',
                  '--output',
                  dest="output_file",
                  default='out',
                  help="write output to FILE",
                  metavar="FILE")
parser.add_option('-c',
                  '--comentions',
                  action="store_true",
                  dest="comentions",
                  help="output co-mentions")
parser.add_option('-f',
                  '--format',
                  dest="format",
                  default='triples',
                  help="format of the output: 'triples' or 'xml'")

(options, args) = parser.parse_args()

if options.input_file:
    documents = [options.input_file]
else:
    documents = [ join(options.input_dir,f) for f in listdir(options.input_dir) if isfile(join(options.input_dir,f)) ]

if not options.output_file:
    output_file = 'out'
else:
    output_file = options.output_file

if (not options.format) or (not options.format in ['triples', 'xml']):
    output_format = 'triples'
else:
    output_format = options.format

triples = list()
root = objectify.Element("frameinstances")
for filename in documents:
    # read file
    log.info("opening file {0}".format(filename))
    with open(filename) as f:
        text = f.read()

    # tokenization
    log.info("Tokenization")
    tokens = tokenize(text)
    if not tokens:
        log.error("error during tokenization of file '{0}', exiting".format(filename))
        continue

    tokenized = "\n".join([' '.join(sentence) for sentence in tokens[:-1]])

    log.info("Parsing")
    drs = get_all(tokenized)
    if not drs:
        log.error("error during the execution of Boxer on file '{0}', exiting".format(filename))
        continue
    log.info("Word sense disambiguation and entity linking")
    synsets, entities = disambiguation(tokenized, drs)
    if synsets==None or entities==None:
		log.error("error during the disambiguation of file '{0}', exiting".format(filename))
		continue

    # extracting co-mentions
    if options.comentions:
        dbpedia_entities = set(map(lambda x: x['entity'], entities))
        for entity1, entity2 in combinations(dbpedia_entities, 2):
            if (entity1 != 'null' and
                entity2 != 'null'):
                triples.append(('<{0}>'.format(entity1), '<{0}#comention>', '<{2}>'.format(config.get('namespace', 'relation'), entity2)))

    # build dictionary of variables
    try:
        variables = dict()
        for predicate in drs['predicates']+drs['namedentities']:
            if not predicate['variable'] in variables:
                variables[predicate['variable']] = []
            for synset in synsets:
                # baseline sysnet alignment
                # TODO: make this smarter
                if predicate['token_start'] == synset['token_start'] and predicate['token_end'] == synset['token_end']:
                    if not synset['synset'] in variables[predicate['variable']]:
                        variables[predicate['variable']].append(synset['synset'])
            for entity in entities:
                # baseline entity alignment
                # TODO: make this smarter
                if predicate['token_start'] == entity['token_start'] and predicate['token_end'] == entity['token_end'] and entity['entity'] != 'null':
                    if not entity['entity'] in variables[predicate['variable']]:
                        variables[predicate['variable']].append(entity['entity'])
    except:
        log.error("error during the alignment on file '{0}', exiting".format(filename))
        continue

    # extract frame instances
    frame_instances = get_frame_instances(variables, drs, thematic_roles)

    # use DRG to get aligned frame instances
    aligned_frames_xml = get_aligned_frames_xml(tokenized, frame_instances, root)

    # scanning relations
    #with open(options.output_file, "a") as f:
    for relation in drs['relations']:
        if (relation['arg1'] in variables and
            relation['arg2'] in variables):
            for entity1, entity2 in product(variables[relation['arg1']],
                                         variables[relation['arg2']]):
                if relation['symbol'] in thematic_roles:
                    # thematic roles
                    synset = entity1.split('/')[-1]
                    try:
                        framelist = frames[synset]
                    except:
                        log.info('No frame found for synset {0}'.format(synset))
                        continue

                    for frame in framelist:
                        if (entity2 != '' and frame != ''):
                            vnrole = relation['symbol']
                            if frame in vn2fn_roles:
                                if vnrole in vn2fn_roles[frame]:
                                    role = vn2fn_roles[frame][vnrole]
                                #else:
                                #    role = "verbnet:{0}".format(vnrole)
                                    triple = ('<{0}>'.format(entity2),
                                              '<{0}#{1}>'.format(config.get('namespace', 'relation'), role),
                                              '<{0}#{1}>'.format(config.get('namespace', 'frame'), frame))
                                    triples.append(triple)
                                    #f.write("{0} {1} {2} .\n".format(*triple))
                else:
                    # other types of relations
                    if (entity2 != '' and entity1 != ''):
                        triple = ('<{0}>'.format(entity1),
                                  '<{0}#{1}>'.format(config.get('namespace', 'relation'), relation['symbol']),
                                  '<{0}>'.format(entity2))
                        triples.append(triple)
                        #f.write("{0} {1} {2} .\n".format(*triple))

log.info('writing output ({0}) on file {1}...'.format(output_format, options.output_file))
with open(output_file, "w") as f:
    if output_format == 'triples':
        for triple in triples:
            f.write("{0} {1} {2} .\n".format(*triple))
    elif output_format == 'xml':
        f.write(aligned_frames_xml)
