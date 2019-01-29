from flask import Flask, request, session, g, redirect, \
     render_template, jsonify
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
    global db
    if db is None:
        db = connect_db()
    return db


def check_login():
    if 'user' in session:
        db = get_db()
        query = 'SELECT (last_login-now() < interval \'7 days\')::INT FROM users WHERE id={}'.format(session['user'])
        try:
            res = du.db_query(db,query,None,False)
            if not res[0][0]:
                session.clear()
                session['message'] = 'Your session has expired. Please log in again.'
                return 0
            else:
                return 1
        except IndexError:
            session.clear()
            return 0
    else:
        return 0


def remove_nonpersistent():
    ret = 0
    rm = []
    for k in session:
        if not k in session['persistent']:
            rm.append(k)
            ret = 1

    for k in rm:
        session.pop(k)

    return ret


@app.route('/')
def root():
    # if the user information is in the session object, redirect to dashboard
    if check_login():
        return redirect('/dashboard')

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
        return redirect('/')
    else:
        # user was found, check password against encoded password and salt
        enc = res[0][2]
        salt = res[0][3]
        matching = du.compare_salted(request.form['lg_password'],enc,salt)
        if not matching:
            # password did not match
            session['message'] = 'Incorrect email or password!'
            return redirect('/')
        else:
            # proceed with login - get user details from database
            query = 'SELECT * FROM user_details WHERE user_id = {};'.format(res[0][0])
            detail = du.db_query(db, query)
            session['fname'] = detail[0][2]
            session['mi'] = detail[0][3]
            session['lname'] = detail[0][4]

            # session object is persistent - existence of email and user indicate user is logged in
            session['email'] = res[0][1]
            session['user'] = res[0][0]

            query = 'UPDATE users SET last_login=now() WHERE id = {};'.format(res[0][0])
            du.db_query(db, query)

            session['message'] = 'Welcome ' + detail[0][2] + '!'

            p = list(session.keys())
            p.append('persistent')
            session['persistent'] = p

    # attempt to go to dashboard (will redirect to root if unsuccessful login)
    return redirect('/dashboard')


@app.route('/logout')
def logout():
    session.clear()
    session['message'] = 'Logout Successful'
    return redirect('/')


@app.route('/dashboard', methods=['GET'])
def dashboard():
    # TODO: display recent sessions
    # TODO: add new 'session info' page to display inforamtion and stats on recent sessions

    if not check_login():
        session['message'] = 'You must be logged in to view the dashboard!'
        return redirect('/')

    if session.get('session_id'):
        session.pop('session_id')

    remove_nonpersistent()

    # clean leftover syncing requests from previous sessions
    db = get_db()
    query = 'UPDATE session_logs SET is_active=0 WHERE user_id = {} and is_active = 1;'.format(session['user'])
    du.db_query(db, query)
    query = 'UPDATE syncing_logs SET is_active=0 WHERE user_id = {} and is_active = 1;'.format(session['user'])
    du.db_query(db, query)

    # display message if available
    msg = ''
    if 'message' in session:
        msg = session['message']
        session['message'] = ''

    # render dashboard page
    return render_template('dashboard.html', message=msg)


@app.route('/session/create', methods=['GET'])
def create_session_landing():
    if not check_login():
        return redirect('/')

    return render_template('createsession.html')


@app.route('/_coding_templates', methods=['GET'])
def get_coding_templates():
    # returns a list of available coding protocols (e.g. BROMP, ObserveME)
    query = 'SELECT * FROM coding_templates'
    res = np.array(du.db_query(get_db(), query))[:, [0, 1]]
    return jsonify(res.tolist())


@app.route('/session/create', methods=['POST'])
def create_session():
    if not check_login():
        return redirect('/')

    # get database handle
    db = get_db()

    class_id = None
    class_code = request.form['class_code']
    if request.form['class_code'] == '':
        # create the class
        query = 'INSERT INTO classrooms (creator_user_id, teacher_name, class_name, grade, subject, n_students) ' \
                'VALUES ({}, \'{}\', \'{}\', \'{}\', \'{}\', {}) RETURNING id;'.format(session['user'],
                                                                                       request.form['teacher'],
                                                                                       request.form['classname'],
                                                                                       request.form['grade'],
                                                                                       request.form['subject'],
                                                                                       request.form['nstudents'])
        res = du.db_query(db, query)
        class_id = res[0][0]
        class_code = str('CL' + hex(class_id)[2:]).upper()  # NOTE: the [2:] index removes the '0x' of the hex value

        query = 'UPDATE classrooms SET code=\'{}\' WHERE id = {};'.format(class_code, class_id)
        du.db_query(db, query)

        # fill out student aliases
        for i in range(int(request.form['nstudents'])):
            query = 'INSERT INTO student_aliases (class_id, student_id) VALUES ({}, {});'.format(class_id, i+1)
            du.db_query(db, query)

    else:
        query = 'SELECT * FROM classrooms WHERE code = {}'.format(class_code)
        res = du.db_query(db, query)

        if len(res) == 0:
            session['message'] = 'The session failed to start: incorrect class code'
            return redirect('/dashboard')

        class_id = res[0][0]

    strict_timer = int('strict_timer' in request.form and request.form['strict_timer'] == 'on')
    randomize_order = int('randomize_order' in request.form and request.form['randomize_order'] == 'on')
    query = 'INSERT INTO sessions (class_id, creator_user_id, coding_template_id, timer_seconds, strict_timer, ' \
            'randomize_order) VALUES ({},{},{},{},{},{}) ' \
            'RETURNING id;'.format(class_id, session['user'], request.form['coding_template'],
                                   request.form['timer_seconds'],  strict_timer,
                                   randomize_order)
    res = du.db_query(db, query)
    session_id = res[0][0]
    session_code = str('SN' + hex(session_id)[2:]).upper()  # NOTE: the [2:] index removes the '0x' of the hex value
    query = 'UPDATE sessions SET code=\'{}\' WHERE id = {};'.format(session_code, session_id)
    du.db_query(db, query)

    # leave any existing sessions
    query = 'UPDATE session_logs SET is_active=0 WHERE user_id={};'.format(session['user'])
    du.db_query(db, query)

    # once the session is created, the creating user joins the session
    query = 'INSERT INTO session_logs (session_id, user_id) VALUES ({},{});'.format(session_id, session['user'])
    du.db_query(db, query)

    session['session_id'] = session_id
    session['class_id'] = class_id
    return redirect('/session/dashboard')


@app.route('/session/join', methods=['POST'])
def join_session():
    if not check_login():
        return redirect('/')

    # get database handle
    db = get_db()

    session_id = int('0x' + request.form['session_code'][2:], 0)
    query = 'SELECT * FROM sessions WHERE id = {}'.format(session_id)
    res = du.db_query(db, query)

    if len(res) == 0:
        session['message'] = 'Session not found'
        return redirect('/dashboard')

    class_id = res[0][1]

    # leave any existing sessions
    query = 'UPDATE session_logs SET is_active=0 WHERE user_id={};'.format(session['user'])
    du.db_query(db, query)

    # join the session
    query = 'INSERT INTO session_logs (session_id, user_id) VALUES ({},{});'.format(session_id, session['user'])
    du.db_query(db, query)

    session['session_id'] = session_id
    session['class_id'] = class_id

    return redirect('/session/dashboard')


@app.route('/_get_coders', methods=['GET'])
def get_session_coders():
    if 'session_id' not in session:
        return jsonify([])

    query = 'SELECT DISTINCT first_name || \' \' || last_name, sl.user_id FROM session_logs sl ' \
            'LEFT OUTER JOIN user_details ud ON ud.user_id = sl.user_id ' \
            'WHERE sl.session_id={} AND sl.user_id != {};'.format(session['session_id'], session['user'])
    res = np.array(du.db_query(get_db(), query))[:, [0, 1]]
    return jsonify(res.tolist())


@app.route('/_get_kappa', methods=['GET'])
def get_kappa():
    if 'coder' not in request.args:
        return jsonify([])

    db = get_db()
    query = 'WITH x AS ( WITH logs AS (SELECT *,row_number() OVER (PARTITION BY coding_section_id, syncing_id) AS r ' \
            'FROM coding_logs cl LEFT OUTER JOIN recorded_codings rc ON rc.coding_log_id = cl.id ' \
            'LEFT OUTER JOIN codings c ON c.id = rc.coding_id LEFT OUTER JOIN coding_sections cs ' \
            'ON cs.id = rc.coding_section_id WHERE cl.submission_time IS NOT NULL  AND cl.syncing_id IS NOT NULL ' \
            'AND rc.recorded_value = 1 AND c.code_value != \'-1\' AND session_id = {} ' \
            'AND user_id IN ({}, {}) ORDER BY coding_section_id, syncing_id, user_id) ' \
            'SELECT * FROM ( SELECT l.*,m.mr FROM logs l ' \
            'LEFT OUTER JOIN (SELECT coding_section_id, syncing_id, max(r) AS mr  ' \
            'FROM logs GROUP BY coding_section_id, syncing_id) AS m ' \
            'ON (l.coding_section_id, l.syncing_id) = (m.coding_section_id, m.syncing_id) ) AS f ' \
            'WHERE f.mr = 2 ) SELECT * FROM ( SELECT DISTINCT syncing_id, coding_section_id, ' \
            'section_name FROM x ) AS a ' \
            'LEFT OUTER JOIN (SELECT display_name, coding_section_id, syncing_id FROM x WHERE user_id = 1) AS u1  ' \
            'ON (u1.coding_section_id, u1.syncing_id) = (a.coding_section_id, a.syncing_id) ' \
            'LEFT OUTER JOIN (SELECT display_name, coding_section_id, syncing_id FROM x WHERE user_id = 2) AS u2 ' \
            'ON (u2.coding_section_id, u2.syncing_id) = ' \
            '(a.coding_section_id, a.syncing_id) ' \
            'LEFT OUTER JOIN coding_section_template_associations cta ON cta.coding_section_id = a.coding_section_id ' \
            'ORDER BY cta.section_position'.format(session['session_id'],session['user'], request.args['coder'])

    res = np.array(du.db_query(db, query))

    ret = []
    _, ind = np.unique(res[:,1], return_index=True)
    sec = res[ind,1]
    for i in range(len(sec)):
        query = 'SELECT DISTINCT display_name FROM coding_section_coding_associations cca ' \
                'LEFT OUTER JOIN codings c ON c.id = cca.coding_id ' \
                'WHERE coding_section_id={} AND c.code_value != \'-1\''.format(sec[i])
        cls = np.array(du.db_query(db, query))[:,0]

        kpa = dict()
        sub = res[np.argwhere(res[:,1] == sec[i]).ravel(),:]
        print(np.array(du.one_hot(sub, cls, 3))[:,-len(cls):])
        kpa['section'] = sub[0,2]
        kpa['kappa'] = '{:.3f}'.format(eval.cohen_kappa_multiclass(np.array(du.one_hot(sub, cls, 3))[:,-len(cls):],
                                                                   np.array(du.one_hot(sub, cls, 6))[:,-len(cls):]))
        for j in range(len(sub[:,3])):
            print('{} : {}'.format(sub[j,3],sub[j,6]))
        print(kpa['kappa'])
        ret.append(kpa)
    return jsonify(ret)


@app.route('/session/dashboard', methods=['GET'])
def session_dashboard():
    if not check_login():
        return redirect('/')

    if 'session_id' not in session:
        session['message'] = 'Failed to join session'
        return redirect('/dashboard')

    db = get_db()

    query = 'UPDATE syncing_logs SET is_active=0 WHERE user_id={};'.format(session['user'])
    du.db_query(db, query)

    query = 'SELECT s.code, c.code, ct.template_name, s.timer_seconds, ' \
            's.strict_timer, s.randomize_order, s.coding_template_id FROM sessions s ' \
            'LEFT OUTER JOIN classrooms c ON c.id = s.class_id ' \
            'LEFT OUTER JOIN coding_templates ct ON ct.id = s.coding_template_id ' \
            'WHERE s.id = {};'.format(session['session_id'])
    res = du.db_query(db, query)

    if len(res) == 0:
        session['message'] = 'Session not found'
        return redirect('/dashboard')

    args = dict()
    args['session_code'] = res[0][0]
    args['class_code'] = res[0][1]
    args['coding_template_name'] = res[0][2]

    session['session_code'] = res[0][0]
    session['class_code'] = res[0][1]
    session['coding_template_name'] = res[0][2]
    session['timer_seconds'] = res[0][3]
    session['strict_timer'] = res[0][4]
    session['randomize_order'] = res[0][5]

    query = 'SELECT * FROM coding_section_template_associations sta ' \
            'LEFT OUTER JOIN coding_sections cs ON cs.id = sta.coding_section_id ' \
            'LEFT OUTER JOIN coding_section_types st ON st.id = cs.coding_section_type_id ' \
            'WHERE sta.coding_template_id = {} ' \
            'ORDER BY sta.section_position;'.format(res[0][6])
    res = du.db_query(db, query)

    sec_info = []
    for sec in res:
        s = dict()
        s['section_name'] = str(sec[5])
        s['type_name'] = str(sec[8]).lower()
        s['css_class'] = '' if s['type_name'] == 'text' else 'option-input ' + s['type_name']
        s['section_id'] = int(sec[4])

        c_query = 'SELECT * FROM coding_section_coding_associations cca ' \
                  'LEFT OUTER JOIN codings c ON c.id = cca.coding_id ' \
                  'WHERE cca.coding_section_id = {} ' \
                  'ORDER BY cca.coding_position;'.format(sec[2])
        c_res = du.db_query(db, c_query)
        s['coding'] = []
        for code in c_res:
            s['coding'].append({'name':str(code[5]), 'value':str(code[5]), 'coding_id':int(code[4])})

        sec_info.append(s)
    session['coding_sections'] = sec_info

    return render_template('sessiondash.html', args=args)


@app.route('/session/timer', methods=['POST'])
def start_timer():
    if not check_login():
        return redirect('/')

    if 'session_id' not in session:
        session['message'] = 'Failed to join session'
        return redirect('/dashboard')

    if 'coding_log_id' not in session:
        return redirect('/session/dashboard')

    db = get_db()
    if 'syncing_id' in session:
        query = 'UPDATE coding_logs SET syncing_id={} WHERE id={};'.format(session['syncing_id'],
                                                                           session['coding_log_id'])
        du.db_query(db, query)

        query = 'SELECT (started_at IS NULL)::INT FROM syncing WHERE id={};'.format(session['syncing_id'])
        res = du.db_query(db, query)
        if int(res[0][0]) == 1:
            query = 'UPDATE syncing SET started_at=now() WHERE id={};'.format(session['syncing_id'])
            du.db_query(db, query)
        session.pop('syncing_id')

    query = 'UPDATE syncing_logs SET is_active=0 WHERE user_id={};'.format(session['user'])
    du.db_query(db, query)

    args = dict()
    args['session_code'] = str(session['session_code'])
    args['class_code'] = str(session['class_code'])
    args['coding_template_name'] = str(session['coding_template_name'])
    args['timer_seconds'] = int(session['timer_seconds'])
    args['strict_timer'] = int(session['strict_timer'])
    args['student_id'] = session['student_id']

    query = 'UPDATE coding_logs SET timer_start=now() WHERE id={};'.format(session['coding_log_id'])
    du.db_query(db, query)

    return render_template('timer.html', args=args)


@app.route('/session/sync', methods=['POST'])
def session_sync_landing():
    if not check_login():
        return redirect('/')

    if 'session_id' not in session:
        session['message'] = 'Failed to join session'
        return redirect('/dashboard')

    if 'student_id' not in session:
        session['message'] = 'Failed to join session'
        return redirect('/dashboard')

    db = get_db()

    # clean up any hanging syncing rows
    query = 'UPDATE syncing SET is_active=0 WHERE session_id={} ' \
            'AND (started_at IS NOT NULL OR now() > created_at + interval \'5 minutes\' ' \
            'OR id NOT IN (' \
            'SELECT id FROM ( ' \
            'SELECT s.id, sum(sg.is_active) AS n_active FROM syncing s ' \
            'LEFT OUTER JOIN syncing_logs sg ON sg.syncing_id = s.id ' \
            'GROUP BY s.id ' \
            ') AS active WHERE n_active IS NOT NULL AND n_active > 0 ' \
            '));'.format(session['session_id'])
    du.db_query(db, query)
    query = 'UPDATE syncing_logs SET is_active=0 WHERE user_id={};'.format(session['user'])
    du.db_query(db, query)

    # look for any active syncing
    query = 'SELECT * FROM syncing WHERE session_id={} AND is_active=1;'.format(session['session_id'])
    res = du.db_query(db, query)

    args = dict()
    args['is_leader'] = 0

    # if none is found, create one
    if len(res) == 0:
        query = 'INSERT INTO syncing (session_id, creator_user_id, student_id) VALUES ({},{},{}) RETURNING id;'.format(
            session['session_id'], session['user'],session['student_id'])
        res = du.db_query(db, query)
        session['syncing_id'] = res[0][0]

        query = 'INSERT INTO syncing_logs (syncing_id, user_id, is_leader) VALUES ({},{},1)'.format(
            session['syncing_id'], session['user'])
        du.db_query(db, query)

        args['is_leader'] = 1

    elif len(res) > 0:
        session['syncing_id'] = res[0][0]
        query = 'INSERT INTO syncing_logs (syncing_id, user_id, is_leader) VALUES ({},{},0)'.format(
            session['syncing_id'], session['user'])
        du.db_query(db, query)
    return render_template('sync.html', args=args)


@app.route('/_syncing', methods=['GET'])
def get_sync_users():
    # returns a list of users within the same sync session
    args = dict()
    args['waiting'] = []
    args['ready'] = []

    db = get_db()

    # print(request.args)

    query = 'UPDATE syncing_logs SET check_in=now() WHERE syncing_id={} AND user_id={};'.format(session['syncing_id'],
                                                                                                session['user'])
    du.db_query(db, query)


    # if the coding started...
    query = 'SELECT (sy.started_at IS NOT NULL)::INT FROM syncing_logs s ' \
            'LEFT OUTER JOIN syncing sy ON sy.id = s.syncing_id ' \
            'WHERE s.syncing_id={} AND s.user_id={};'.format(session['syncing_id'], session['user'])
    res = du.db_query(db, query)

    args['redirect'] = 'none'
    args['method'] = 'none'
    if int(res[0][0]) == 1:
        if 'is_ready' in request.args and int(request.args['is_ready'])==1:
            # if i was ready...
            args['redirect'] = '/session/timer'
            args['method'] = 'post'
        else:
            # if it started without me...
            session.pop('syncing_id')
            args['redirect'] = '/session/observe'
            args['method'] = 'get'

        return jsonify(args)


    query = 'SELECT (check_in > now() - interval \'30 seconds\')::INT FROM syncing_logs ' \
            'WHERE syncing_id={} AND is_active=1 AND is_leader=1;'.format(session['syncing_id'])
    res = du.db_query(db, query)
    if len(res) == 0 or int(res[0][0]) == 0:
        # the leader has disconnected, find a new leader
        query = 'UPDATE syncing_logs SET is_active=0, is_leader=0 ' \
                'WHERE syncing_id={} AND is_leader=1;'.format(session['syncing_id'])
        du.db_query(db, query)

        query = 'SELECT * FROM syncing_logs WHERE syncing_id={} AND is_active=1 ' \
                'ORDER BY joined_at;'.format(session['syncing_id'])
        res = du.db_query(db, query)
        query = 'UPDATE syncing_logs SET is_leader=1 WHERE id={}'.format(res[0][0])
        du.db_query(db, query)

    query = 'SELECT is_leader FROM syncing_logs WHERE syncing_id={} AND user_id={};'.format(session['syncing_id'],
                                                                                            session['user'])
    args['is_leader'] = int(du.db_query(db,query)[0][0])

    if 'is_ready' in request.args:
        if int(request.args['is_ready'])==1:
            query = 'UPDATE syncing_logs SET ready_at=now() ' \
                    'WHERE syncing_id={} AND user_id={};'.format(session['syncing_id'], session['user'])
        else:
            query = 'UPDATE syncing_logs SET ready_at=NULL ' \
                    'WHERE syncing_id={} AND user_id={};'.format(session['syncing_id'], session['user'])
        du.db_query(db,query)

    query = 'SELECT first_name FROM syncing_logs s ' \
            'LEFT OUTER JOIN user_details ud ON ud.user_id = s.user_id ' \
            'WHERE is_active=1 AND s.syncing_id = {} AND ready_at IS NULL;'.format(session['syncing_id'])
    args['waiting'] = [i[0] for i in du.db_query(db, query)]

    query = 'SELECT first_name FROM syncing_logs s ' \
            'LEFT OUTER JOIN user_details ud ON ud.user_id = s.user_id ' \
            'WHERE is_active=1 AND s.syncing_id = {} AND ready_at IS NOT NULL;'.format(session['syncing_id'])
    args['ready'] = [i[0] for i in du.db_query(db, query)]

    args['session_code'] = session['session_code']

    query = 'SELECT sy.student_id FROM syncing_logs s ' \
            'LEFT OUTER JOIN syncing sy ON sy.id = s.syncing_id ' \
            'WHERE s.syncing_id={} AND s.user_id={};'.format(session['syncing_id'], session['user'])
    res = du.db_query(db, query)
    args['student_id'] = res[0][0]

    session['student_id'] = int(args['student_id'])

    return jsonify(args)


@app.route('/session/observe', methods=['GET'])
def session_observe():
    if not check_login():
        return redirect('/')

    if 'session_id' not in session:
        session['message'] = 'Failed to join session'
        return redirect('/dashboard')

    if 'coding_log_id' in session:
        session.pop('coding_log_id')

    if 'syncing_id' in session:
        session.pop('syncing_id')

    db = get_db()
    query = 'UPDATE syncing_logs SET is_active=0 WHERE user_id={};'.format(session['user'])
    du.db_query(db, query)

    # determine who to display and show the observing menu (pre timer)
    args = dict()
    args['session_code'] = str(session['session_code'])
    args['class_code'] = str(session['class_code'])
    args['coding_template_name'] = str(session['coding_template_name'])

    if 'n_students' not in session:
        query = 'SELECT * FROM classrooms WHERE id = {};'.format(session['class_id'])
        res = du.db_query(db, query)
        session['n_students'] = int(res[0][6])

    if 'student_id' not in session:
        session['student_id'] = 1 if not session['randomize_order'] else \
            np.random.randint(1, session['n_students'] + 1, 1)[0]
    else:
        if len(request.args) > 0 or 'recorded' in session:
            session['student_id'] = session['student_id'] + 1 if not session['randomize_order'] else \
                np.random.randint(1, session['n_students'] + 1, 1)[0]
            if session['student_id'] > session['n_students']:
                session['student_id'] = 1

    if 'recorded' in session:
        session.pop('recorded')

    session['student_id'] = int(session['student_id'])
    args['student_id'] = session['student_id']

    query = 'SELECT * FROM student_aliases ' \
            'WHERE class_id = {} AND student_id = {};'.format(session['class_id'],session['student_id'])
    res = du.db_query(db, query)
    alias_id = res[0][0]

    query = 'INSERT INTO coding_logs (session_id, class_id, user_id, student_id, student_alias_id) ' \
            'VALUES ({},{},{},{},{}) RETURNING id;'.format(session['session_id'], session['class_id'], session['user'],
                                                           session['student_id'], alias_id)
    res = du.db_query(db, query)
    session['coding_log_id'] = int(res[0][0])

    return render_template('observe.html', args=args)


@app.route('/_coding_template_sections', methods=['GET'])
def get_coding_template_sections():
    # returns a list of available coding protocols (e.g. BROMP, ObserveME)
    if 'coding_sections' not in session:
        return jsonify([])
    return jsonify(session['coding_sections'])


@app.route('/session/observe', methods=['POST'])
def session_record_landing():
    if not check_login():
        return redirect('/')

    if 'session_id' not in session:
        session['message'] = 'Failed to join session'
        return redirect('/dashboard')

    db = get_db()
    query = 'UPDATE syncing_logs SET is_active=0 WHERE user_id={};'.format(session['user'])
    du.db_query(db, query)

    args = dict()
    args['session_code'] = str(session['session_code'])
    args['class_code'] = str(session['class_code'])
    args['coding_template_name'] = str(session['coding_template_name'])
    args['timer_seconds'] = int(session['timer_seconds'])
    args['strict_timer'] = int(session['strict_timer'])
    args['randomize_order'] = int(session['randomize_order'])
    args['student_id'] = session['student_id']

    query = 'UPDATE coding_logs SET coding_time=now() WHERE id={};'.format(session['coding_log_id'])
    du.db_query(db, query)

    return render_template('coding.html', args=args)


@app.route('/session/record', methods=['POST'])
def session_record_coding():
    if not check_login():
        return redirect('/')

    if 'session_id' not in session:
        session['message'] = 'Failed to join session'
        return redirect('/dashboard')

    if 'coding_log_id' not in session:
        return redirect('/session/dashboard')

    for i in request.form:
        print('{} : {}'.format(i,request.form[i]))

    db = get_db()
    query = 'UPDATE syncing_logs SET is_active=0 WHERE user_id={};'.format(session['user'])
    du.db_query(db, query)

    query = 'UPDATE coding_logs SET submission_time=now() WHERE id={};'.format(session['coding_log_id'])
    du.db_query(db, query)

    template = 'INSERT INTO recorded_codings (coding_log_id, coding_section_id, coding_id, recorded_value) ' \
               'VALUES ({}, {}, {}, {});'

    for sec in session['coding_sections']:
        for c in sec['coding']:
            key = sec['section_name'] if sec['type_name'] == 'radio' else c['name']
            query = template.format(session['coding_log_id'], sec['section_id'], c['coding_id'],
                                    int(key in request.form and request.form[key] == c['value']))
            du.db_query(db, query)

    session['recorded'] = 1

    return redirect('/session/observe')


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
