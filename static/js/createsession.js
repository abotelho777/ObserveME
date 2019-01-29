
var $teacher = $("#teacher");
var $classname = $("#classname");
var $nstudents = $("#nstudents");
var $sesscode = $("#session_code");

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
    isFilled($sesscode);
    return (isFilled($sesscode));
}

function showClassForm() {
    document.getElementById("classField").style.display = "none";
    document.getElementById("classBtn").style.display = "none";
    document.getElementById("classForm").style.display = "block";
    document.getElementById("class_code").setAttribute('value','')
}

$teacher.focus().keyup(function() {isFilled($teacher);});
$classname.focus().keyup(function() {isFilled($classname);});
$nstudents.focus().keyup(function() {isFilled($nstudents);});
$sesscode.focus().keyup(function() {isFilled($sesscode);});



