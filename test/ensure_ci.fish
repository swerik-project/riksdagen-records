echo [INFO]: Check that all unittest files are included in the .github/workflows folder...
set exitcode 0
for pot_testfile in test/*.py
    set contents (cat $pot_testfile)
    if string match -q  -- '*unittest*' $contents
        set ci_stuff (cat .github/workflows/*.*)
        set test_name (string replace test/ "" $pot_testfile)
        set test_name (string replace ".py" "" $test_name)
        if string match -q  -- "*"$test_name"*" $ci_stuff
            echo [INFO]: $test_name found in the CI
        else
            echo [ERROR]: $test_name not found in the CI
            set exitcode 1
        end
    end
end

exit $exitcode