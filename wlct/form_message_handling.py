'''
Created on Nov 10, 2015

@author: Brendan Flynn
'''

class FormMessageBase(object):
    '''
    classdocs

    message: the main message for a view

    errors: a list of all the error messages captured in a view
    '''

    def __init__(self, initial_msg):
        '''
        Constructor
        '''
        self.msgs = dict()
        if isinstance(initial_msg, dict):
            self.msgs = initial_msg

    def log_errors(self):
        ''' TODO add a method that talks to a logging model and logs the current page errors '''

class FormError(FormMessageBase):
    # Returns HTML style of the message to return
    html_style = 'alert alert-danger'

class FormConfirmation(FormMessageBase):
    # Returns HTML style of the message to return
    html_style = 'alert alert-success'