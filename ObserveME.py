from flask import Flask, request, session, g, redirect, \
     render_template
import datautility as du
import evaluationutility as eval
from numpy import random as rand
import os
import time
import json
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score,cohen_kappa_score

app = Flask(__name__)
app_args = du.read_paired_data_file(os.path.dirname(os.path.abspath(__file__))+'\config.txt')
app.secret_key = app_args['secret_key']
db = None


def connect_db():
    db = du.db_connect(app_args['db_name'], app_args['username'], app_args['password'],
                       host=app_args['host'], port=app_args['port'])
    return db

def get_db():
    if not hasattr(g, 'db'):
        g.db = connect_db()
    return g.db

@app.route('/')
def root():
    msg = ''
    # Display indicator message if available
    if 'message' in session:
        msg = session['message']
        session['message'] = ''
    # Render login page
    return render_template('index.html', message=msg)


@app.route('/register', methods=['GET'])
def registration_landing():
    # render registration page
    return render_template('register.html')


@app.route('/register', methods=['POST'])
def register():
    # get database handle
    db = get_db()

    # check to see if the user already exists using the entered email address
    query = 'SELECT * FROM users WHERE email=\'{}\';'.format(request.form['Email'])
    res = du.db_query(db, query)
    if len(res) > 0:
        # redirect to login page with message if user is found
        session['message'] = 'A user with that email is already registered!'
        return redirect('/')

    # if not found, generate encrypted password and salt and add entry to the database
    password, salt = du.get_salted(request.form['password'])
    query = 'INSERT INTO users (email, encrypted_password, salt) VALUES (\'{}\',\'{}\',\'{}\');'.format(
        request.form['Email'], password, salt)
    if du.db_query(db,query) is None:
        session['message'] = 'Oops! We are unable to connect to the database.'
    else:
        # check to ensure that the user was added
        query = 'SELECT * FROM users WHERE email=\'{}\';'.format(request.form['Email'])
        res = du.db_query(db, query)
        if len(res) == 0:
            # if the user is not found, redirect to login page with message
            session['message'] = 'Oops! Something went wrong trying to register your account.'
            redirect('/')
        else:
            session['message'] = 'You are now registered!'

        # add associated user details to database (low priority, no additional check made)
        query = 'INSERT INTO user_details (user_id, first_name, middle_initial, last_name) VALUES ' \
                '({},\'{}\',\'{}\',\'{}\');'.format(res[0][0], request.form['fname'], request.form['mi'],
                                                    request.form['lname'])
        du.db_query(db, query)

    # return to the login page
    return redirect('/')


@app.route('/login', methods=['POST'])
def login():
    # get database handle
    db = get_db()

    # search database for the user
    query = 'SELECT * FROM users WHERE email=\'{}\';'.format(request.form['Email'])
    res = du.db_query(db, query)

    if len(res) == 0:
        # user was not found
        session['message'] = 'Incorrect email or password!'
    else:
        # user was found, check password against encoded password and salt
        enc = res[0][2]
        salt = res[0][3]
        matching = du.compare_salted(request.form['lg_password'],enc,salt)
        if not matching:
            # password did not match
            session['message'] = 'Incorrect email or password!'
        else:
            # proceed with login - get user details from database
            # TODO: check that user_details entry exists and fill with default values if not found
            query = 'SELECT * FROM user_details WHERE user_id = {};'.format(res[0][0])
            detail = du.db_query(db, query)
            session['fname'] = detail[0][2]
            session['mi'] = detail[0][3]
            session['lname'] = detail[0][4]

            # session object is persistent - existence of email and user indicate user is logged in
            # TODO: add login timestamp to session object to implement login expiration
            session['email'] = res[0][1]
            session['user'] = res[0][0]

            session['message'] = 'Welcome ' + detail[0][2] + '!'

    # attempt to go to dashboard (will redirect to root if unsuccessful login)
    return redirect('/dashboard')


@app.route('/dashboard', methods=['GET'])
def dashboard():
    # TODO: display recent sessions
    # TODO: add new 'session info' page to display inforamtion and stats on recent sessions

    # if the user information is not in the session object, redirect to root
    if not ('email' in session and len(session['email']) > 0):
        session['message'] = 'You must be logged in to view the dashboard!'
        return redirect('/')

    # clean leftover syncing requests from previous sessions
    db = get_db()
    query = 'DELETE FROM syncing WHERE coder_user_id={};'.format(session['user'])
    du.db_query(db, query)

    # display message if available
    msg = ''
    if 'message' in session:
        msg = session['message']
        session['message'] = ''

    # render dashboard page
    return render_template('dashboard.html', message=msg)


@app.route('/addclass', methods=['GET'])
def add_class_landing():
    # ensure user is logged in and redirect if not
    if 'user' not in session:
        return redirect('/dashboard')

    # get database handle
    db = get_db()

    # find the last unfinished class entry from the current user and use this if found
    query = 'SELECT * FROM classrooms WHERE code IS NULL AND creator_user_id = {};'.format(session['user'])
    res = du.db_query(db, query)

    if len(res) == 0:
        # no unfinished logs were found, create a new log
        query = 'INSERT INTO classrooms (creator_user_id) VALUES ({});'.format(session['user'])
        du.db_query(db, query)

        # select the newly added row (id will be used for class code)
        query = 'SELECT * FROM classrooms WHERE code IS NULL AND creator_user_id = {};'.format(session['user'])
        res = du.db_query(db, query)

    # generate the class code: simply 'CL' followed by the hex of row id from the classrooms table
    code = str('CL' + hex(res[0][0])[2:]).upper()

    # render class creation page
    return render_template('addclass.html', code=code)


@app.route('/addclass', methods=['POST'])
def add_class():
    # get database handle
    db = get_db()

    # get the class id from the generated class code
    class_id = int('0x' + request.form['cl_code'][2:], 0)

    # update the row with the form information
    query = 'UPDATE classrooms SET teacher_name=\'{}\', class_name=\'{}\', grade=\'{}\',subject=\'{}\',n_students={},' \
            'code=\'{}\', created_at=now() WHERE id = {};'.format(request.form['teacher'], request.form['classname'],
                                                                  request.form['grade'], request.form['subject'],
                                                                  request.form['nstudents'], request.form['cl_code'],
                                                                  class_id)
    du.db_query(db, query)

    # return to the dashboard and display the created class code for user feedback and reference
    session['message'] = 'Class "{}" has been created!'.format(request.form['cl_code'])
    return redirect('/dashboard')


@app.route('/session', methods=['GET'])
def session_landing():
    """
    session_landing handles all state changes within the session, including syncing and timer initialization
    """
    # TODO: reformulate 'session' conceptual object and add database table to log coders joining a session
    # TODO: rewrite syncing functionality (currently relies on page refresh to search for second coder)
    # TODO: add parameter for timer duration
    # TODO: add timer duration to coding_logs table in database
    # TODO: allow user to define timer duration
    # TODO: include measure of kappa for the current session (default as hidden, but allow expandable)

    if 'user' not in session:
        return redirect('/dashboard')

    if 'class_code' not in request.args:
        return redirect('/dashboard')

    args = dict()
    db = get_db()

    # TODO: ensure user is signed in before beginning session

    # get class information (code, number of students, etc)
    session['class_code'] = str(request.args.get('class_code')).upper()
    query = 'SELECT * FROM classrooms WHERE upper(code) = upper(\'{}\');'.format(str(session['class_code']).upper())
    res = du.db_query(db, query)

    if len(res) == 0:
        # if the class is not found, return to the dashboard
        session['message'] = 'The class "{}" does not exist!'.format(session['class_code'])
        return redirect('/dashboard')

    nstudents = int(float(res[0][6]))
    session['class_id'] = res[0][0]

    # action denotes user input from the page
    if 'action' in request.args:
        if request.args['action'] == '1':  # user clicked the 'Start' button to start timer
            args['action'] = str(request.args['action'])
            args['student_id'] = session['current']
            args['class_id'] = session['class_code']

            # create entry for coding logs (NOTE: -1 log_state denotes unfinished 'Start' action
            query = 'INSERT INTO coding_logs (class_id, coder_user_id, student_id,log_state) ' \
                    'VALUES ({},{},{},-1);'.format(
                session['class_id'], session['user'], session['current'])
            du.db_query(db,query)

            # user transitions into session (countdown) state
            # render the session page and begin timer (handled in the javascript on the page)
            return render_template('session.html', args=args)
        elif request.args['action'] == '2':  # user clicked the 'Sync' button to sync with another coder

            # check to see if another coder has already requested a sync in the same session
            query = 'SELECT * FROM syncing WHERE class_id={} ORDER BY sync_timestamp ASC;'.format(session['class_id'])
            res = du.db_query(db, query)

            if len(res) == 0:
                # if no sync is found, create a sync request - user transitions to session (waiting) state
				
                query = 'INSERT INTO syncing (class_id, coder_user_id, student_id) VALUES ({},{},{});'.format(
                    session['class_id'],session['user'],session['current'])
                du.db_query(db, query)

                args['action'] = '2'  # waiting
                args['class_id'] = session['class_code']
                args['student_id'] = session['current']

                # render session page in 'waiting' state
                return render_template('session.html', args=args)
            elif len(res) == 1 and res[0][2] != session['user']:
                # sync request was found from a different user - user transitions to session (countdown)

                # answer sync request from other user by creating a second entry
                query = 'INSERT INTO syncing (class_id, coder_user_id, student_id) VALUES ({},{},{});'.format(
                    session['class_id'], session['user'], session['current'])
                du.db_query(db, query)
                session['current'] = res[0][3]
                args['action'] = '5'  # syncing
                args['class_id'] = session['class_code']
                args['student_id'] = session['current']

                # create empty coding log (-5 log state denotes unfinished 'Sync' action)
                query = 'INSERT INTO coding_logs (class_id, coder_user_id, student_id,log_state) ' \
                        'VALUES ({},{},{},-5);'.format(session['class_id'], session['user'], session['current'])
                du.db_query(db, query)

                # render session page in 'countdown' state
                return render_template('session.html', args=args)
            elif len(res) > 1:
                # sync request was found with multiple users - another user answered the sync request
                student = res[0][3]
                if res[0][2] == session['user']:
                    # remove the sync request
                    query = 'DELETE FROM syncing WHERE class_id={};'.format(session['class_id'])
                    du.db_query(db,query)
                session['current'] = res[0][3]
                args['action'] = '5'  # syncing
                args['class_id'] = session['class_code']
                args['student_id'] = session['current']

                # create empty coding log (-5 log state denotes unfinished 'Sync' action)
                query = 'INSERT INTO coding_logs (class_id, coder_user_id, student_id,log_state) ' \
                        'VALUES ({},{},{},-5);'.format(
                    session['class_id'], session['user'], session['current'])
                du.db_query(db, query)
                # render session page in 'countdown' state
                return render_template('session.html', args=args)
            else:
                # sync request was made and user is still waiting for a second coder
                args['action'] = '2'  # waiting
                args['class_id'] = session['class_code']
                args['student_id'] = session['current']
                # render session page in 'waiting' state
                return render_template('session.html', args=args)

        elif request.args['action'] == '3':  # user clicked 'Skip' button
            # transition to session landing page and go to next student
            return redirect('/session?class_code={}'.format(session['class_code']))

        elif request.args['action'] == '4':  # restart same student ('Back' button selected when waiting for coder)
            # delete the sync request that had been made
            query = 'DELETE FROM syncing WHERE class_id={} AND coder_user_id={};'.format(
                session['class_id'], session['user'])
            du.db_query(db, query)

            args['action'] = '0'  # no action
            args['class_id'] = session['class_code']
            args['student_id'] = session['current']
            args['class_id'] = session['class_code']
            # render session landing page without proceeding to the next student
            return render_template('session.html', args=args)
        else:
            # no action has been found (in session landing state)
            args['action'] = '0'  # no action

            # check to see if another coder is waiting with a sync request
            query = 'SELECT * FROM syncing WHERE class_id={} ORDER BY sync_timestamp ASC;'.format(session['class_id'])
            res = du.db_query(db, query)
            if len(res) > 0:
                # if found, automatically sync to the waiting coder
                session['current'] = res[0][3]

                if res[0][2] == session['user']:
                    # if the found entry is from the current user, delete the request
                    query = 'DELETE FROM syncing WHERE coder_user_id={};'.format(session['user'])
                    du.db_query(db, query)
                else:
                    # if found entry is from a different coder, answer the sync request
                    query = 'INSERT INTO syncing (class_id, coder_user_id, student_id) VALUES ({},{},{});'.format(
                        res[0][1], session['user'], session['current'])
                    du.db_query(db, query)

                args['action'] = '5'  # syncing
                args['class_id'] = session['class_code']
                args['student_id'] = session['current']
                query = 'INSERT INTO coding_logs (class_id, coder_user_id, student_id,log_state) ' \
                        'VALUES ({},{},{},-5);'.format(
                    session['class_id'], session['user'], session['current'])
                du.db_query(db, query)

                # render session page in 'countdown' state
                return render_template('session.html', args=args)
            else:
                # no sync requests found - proceed to render landing page
                pass
    else:
        # action does not exist in arguments - proceed with normal session landing page
        args['action'] = '0'  # no action

        # check to see if there are any sync requests
        query = 'SELECT * FROM syncing WHERE class_id={} ORDER BY sync_timestamp ASC;'.format(session['class_id'])
        res = du.db_query(db, query)
        if len(res) > 0:
            # sync request was found
            session['current'] = res[0][3]

            if res[0][2] == session['user']:
                # if the request is from the current user, delete the request (session has no action)
                query = 'DELETE FROM syncing WHERE coder_user_id={};'.format(session['user'])
                du.db_query(db, query)
            else:
                # if the request is from someone else, answer the sync request
                query = 'INSERT INTO syncing (class_id, coder_user_id, student_id) VALUES ({},{},{});'.format(
                    res[0][1], session['user'], session['current'])
                du.db_query(db, query)

            args['action'] = '5' # sync
            args['class_id'] = session['class_code']
            args['student_id'] = session['current']

            # create an empty coding log (-5 log state denotes unfinished 'Sync' action)
            query = 'INSERT INTO coding_logs (class_id, coder_user_id, student_id,log_state) ' \
                    'VALUES ({},{},{},-5);'.format(
                session['class_id'], session['user'], session['current'])
            du.db_query(db, query)

            # render the session page in the 'countdown' state
            return render_template('session.html', args=args)

    # reaching this point means there is no sync request
    # select a random student for observation
    session['current'] = str(rand.randint(1, nstudents + 1, 1)[0])
    args['class_id'] = session['class_code']
    args['student_id'] = session['current']

    ########################################################################################################
    # Querying to find the Kappa value
    try:
        ########################################################################################################
        # Querying to find the Kappa value

        query = 'select date_trunc(\'minute\',coding_timestamp) as coding_timestamp_trunc,* from coding_logs where date(coding_timestamp)= date(now()) and log_state=5 and submission_timestamp is not null ;'
        df = pd.DataFrame(du.db_query(db, query))
        if (len(df.index) != 0):

            df.columns = ['coding_timestamp_trunc', 'id', 'class_id', 'coder_user_id', 'student_id', 'student_name',
                          'coding_timestamp', 'submission_timestamp', 'shows_mental_effort', 'is_on_task',
                          'affect_state',
                          'focus', 'is_writing', 'rec_aid', 'hand_raised', 'collab_peer', 'is_fidgeting',
                          'teacher_speaking', 'log_state']

            # session['user']

            num = (df['coder_user_id'].tolist())
            users = list(set(df['coder_user_id'].tolist()))
            coders_df = []
            user_df = None
            for i in users:
                if i == session['user']:
                    user_df = df.loc[df['coder_user_id'] == i]
                    user_df = user_df.sort_values(by=['coding_timestamp'], ascending=False)
                else:
                    df1 = df.loc[df['coder_user_id'] == i]
                    df1 = df1.sort_values(by=['coding_timestamp'], ascending=False)
                    coders_df.append(df1)

            for u in coders_df:
                coder1 = user_df
                coder2 = u
                # print(users)
                # print(session['user'])
                # One hot encoding of the dataframe for each of the coders
                # coder1 = pd.get_dummies(data=coder1, columns=['affect_state', 'focus'])
                coder1_new = coder1.add_prefix('coder1_')
                # coder2 = pd.get_dummies(data=coder2, columns=['affect_state', 'focus'])
                coder2_new = coder2.add_prefix('coder2_')
                # Getting the features on which kappa has to be calculated
                coder1_features = coder1.columns
                coder1_features = coder1_features.tolist()
                coder2_features = coder2.columns
                coder2_features = coder2_features.tolist()

                coder1_features = coder1_features[8:]
                coder2_features = coder2_features[8:]

                # Finding common features and removing focus and affect state features, They will be handled seperately
                common_features = list(set(coder1_features).intersection(set(coder2_features)))
                # print(set(coder1_features))
                # affect = ["affect_state_unknown", "affect_state_bored", "affect_state_frustrated", "affect_state_concentrating",
                #           "affect_state_confused"]
                # focus = ["focus_screen", "focus_unknown", "focus_teacher", "focus_peer", "focus_work"]
                # aff = []
                # foc = []
                # for i in common_features:
                #     if i in affect:
                #         aff.append(i)
                #         common_features.remove(i)
                #     if i in focus:
                #         foc.append(i)
                #         common_features.remove(i)

                # Renaming the common columns so that we can use them in merge function
                coder1_new['coding_timestamp_trunc'] = coder1_new['coder1_coding_timestamp_trunc']
                del coder1_new['coder1_coding_timestamp_trunc']
                coder2_new['coding_timestamp_trunc'] = coder2_new['coder2_coding_timestamp_trunc']
                del coder2_new['coder2_coding_timestamp_trunc']
                coder1_new['student_id'] = coder1_new['coder1_student_id']
                del coder1_new['coder1_student_id']
                coder2_new['student_id'] = coder2_new['coder2_student_id']
                del coder2_new['coder2_student_id']
                merged = coder1_new.merge(coder2_new, on=['coding_timestamp_trunc', 'student_id'], how='inner')

                query = 'SELECT first_name FROM user_details WHERE user_id = {};'.format(
                    list(set(coder2['coder_user_id'].tolist()))[0])
                name = np.array(du.db_query(db, query)).ravel()[0]
                # Adding kappa values to args
                for i in common_features:
                    a = "coder1_" + i
                    b = "coder2_" + i

                    # print(len(merged[a]))

                    npa = np.array(merged[a])
                    npb = np.array(merged[b])
                    try:
                        # print(i)
                        # print(merged[a])
                        # print(merged[b])
                        f = np.argwhere([j != -1 and j != 'unknown' for j in npa]).ravel()
                        # print(f)
                        npa = npa[f]
                        npb = npb[f]

                        f = np.argwhere([j != -1 and j != 'unknown' for j in npb]).ravel()
                        # print(f)
                        npa = npa[f]
                        npb = npb[f]
                    except ValueError:
                        # print('skipped')
                        continue

                    # print(npa)

                    # print(npb)
                    # print('----------------')
                    try:
                        args[i] = '{} | {}: {:<.3f}'.format(args[i], name, cohen_kappa_score(npa, npb))
                    except KeyError:
                        args[i] = '{}: {:<.3f}'.format(name, cohen_kappa_score(npa, npb))

    except:
        pass

    # render session in 'landing' state
    return render_template('session.html', args=args)


@app.route('/session', methods=['POST'])
def log_session():
    # TODO: (very low priority) define codings in database table and create a coding builder
    # TODO: allow for offline recording of coding logs and update when reconnected

    args = dict()
    db = get_db()

    # get all the fields of the request form (observation codings)
    for i in request.form:
        args[i] = request.form[i]

    # define the string variables for easier sql generation
    str_vars = ['student_name', 'affect_state', 'focus']

    args['class_id'] = session['class_id']
    args['coder_user_id'] = session['user']

	# find most recent empty log from user (will correspond with the row generated in the previous state)
    query = 'SELECT * FROM coding_logs WHERE log_state < 0 ORDER BY coding_timestamp DESC;'
    res = du.db_query(db,query)

    if len(res) == 0:
        # if no log is found, generate the full row
        var_list = list(args.keys())[0]
        val_list = '\'{}\''.format(args[list(args.keys())[0]]) if list(args.keys())[0] in str_vars else '{}'.format(
            args[list(args.keys())[0]])

        for i in range(1, len(args.keys())):
            var_list += ',' + list(args.keys())[i]
            val_list += ',\'{}\''.format(args[list(args.keys())[i]]) if list(args.keys())[
                                                                            i] in str_vars else ',{}'.format(
                args[list(args.keys())[i]])

        query = 'INSERT INTO coding_logs (' + var_list + ') VALUES (' + val_list + ');'
        du.db_query(db,query)
    else:
        # empty corresponding log is found, fill in the missing information (and flip the sign of the log state)
        set_list = 'submission_timestamp=now(),log_state={}'.format(-1*res[0][17])

        for i in range(len(args.keys())):
            set_list += ',' + list(args.keys())[i] + '=' + \
                        ('\'{}\''.format(
                            args[list(args.keys())[i]]) if list(args.keys())[i] in str_vars else '{}'.format(
                            args[list(args.keys())[i]]))

        query = 'UPDATE coding_logs SET {} WHERE id = {};'.format(set_list, res[0][0])
        du.db_query(db,query)
    

            
    # redirect to the session landing
    return redirect('/session?class_code={}'.format(session['class_code']))


if __name__ == '__main__':
    app.run(threaded=True, debug=False, host='0.0.0.0',port='5000')
