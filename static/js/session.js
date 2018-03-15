
var $teacher = $("#teacher");
var $classname = $("#classname");
var $nstudents = $("#nstudents");

var $classcode = $("#class_code");

// var action = '{{ action }}';


// document.getElementById("coding_form").style.display = (action === '1' ? "default" : "none");


function checkDisplay() {
    document.getElementById("coding_form").style.display = (action === '1' ? "block" : "none");
}

//Hide hints
$("form span").hide();


function isNumeric(field) {

    var num = !isNaN(field.val());

    if (!num) {
        field.next().show();
    }
    else {
        field.next().hide();
    }

    return num;
}

function isFilled(field) {
    var filled = field.val().length > 0;

    if (!filled) {
        field.next().show();
    }
    else {
        field.next().hide();
    }
    return filled;
}

function canSubmit() {
    isFilled($teacher);
    isFilled($classname);
    isFilled($nstudents);

    return (isFilled($teacher) && isFilled($classname) && isFilled($nstudents) && isNumeric($nstudents));
}

function canStart() {
    isFilled($classcode);

    return (isFilled($classcode));
}

$teacher.focus().keyup(function() {isFilled($teacher);});
$classname.focus().keyup(function() {isFilled($classname);});
$nstudents.focus().keyup(function() {isFilled($nstudents);});

$classcode.focus().keyup(function() {isFilled($classcode);});



