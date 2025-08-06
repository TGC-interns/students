import streamlit as st
from firebase_helper import init_firestore
import google.generativeai as genai
import json
import os
import random
import time

st.set_page_config(page_title="Exit Ticket - Student Portal", layout="wide")

from config import DEFAULT_QUESTIONS_COUNT
from ui import app_ui

db = init_firestore()

GOOGLE_API_KEY = st.secrets["api_keys"]["google_api_key"]

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

def main():
    st.markdown(
        app_ui,
        unsafe_allow_html=True
    )
    
    # Direct to student dashboard - no login required
    student_dashboard()

def student_dashboard():
    st.title("🎓 Student Portal - Exit Ticket")
    st.markdown("Enter the ticket code provided by your teacher to start the exit ticket.")

    # Initialize session state for exit tickets
    for key, default in {
        "ticket_data": None,
        "ticket_current_question": 0,
        "ticket_user_answers": {},
        "ticket_quiz_completed": False,
        "ticket_show_feedback": False,
        "ticket_last_user_answer": None
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default

    # Flow control for exit tickets
    if st.session_state.ticket_data is None:
        show_ticket_input_page()

    elif not st.session_state.ticket_quiz_completed:
        # 🔁 Randomly select only 3 questions once - BUT KEEP OPTIONS ORDER
        if 'ticket_initialized' not in st.session_state:
            all_questions = st.session_state.ticket_data['questions']
            # Select random questions but preserve their internal structure
            selected_questions = random.sample(all_questions, min(3, len(all_questions)))
            
            # Ensure each question maintains its original option order
            for question in selected_questions:
                # Don't modify the options dictionary - keep A, B, C, D order
                pass  # Options remain in original order
            
            st.session_state.ticket_data['questions'] = selected_questions
            st.session_state.ticket_current_question = 0
            st.session_state.ticket_user_answers = {}
            st.session_state.ticket_quiz_completed = False
            st.session_state.ticket_initialized = True

        show_ticket_quiz_page()

    else:
        show_ticket_results_page()

def show_ticket_input_page():
    """Page for students to enter ticket ID and name"""
    
    st.markdown("### 🎫 Enter Ticket Information")
    
    with st.form("ticket_access_form"):
        st.markdown("#### Step 1: Enter Ticket Code")
        ticket_id = st.text_input(
            "Ticket Code",
            placeholder="e.g., A3X9K2",
            help="Enter the 6-character ticket code provided by your teacher (case insensitive)",
            max_chars=6
        ).upper().strip()
        
        st.markdown("#### Step 2: Enter Your Name")
        student_name = st.text_input(
            "Your Name",
            placeholder="Enter your full name",
            help="This will be used to track your responses"
        ).strip()
        
        submitted = st.form_submit_button("🚀 Start Exit Ticket", type="primary")
        
        if submitted:
            # Validate inputs
            if not ticket_id:
                st.error("Please enter a ticket code.")
                return
            
            if len(ticket_id) != 6:
                st.error("Ticket code should be 6 characters long.")
                return
                
            if not student_name:
                st.error("Please enter your name.")
                return
            
            # Retrieve ticket from database
            from firebase_helper import get_exit_ticket, check_student_already_attempted
            with st.spinner("Loading exit ticket..."):
                ticket_data = get_exit_ticket(db, ticket_id)
                
                if ticket_data:
                    if ticket_data.get('status') != 'active':
                        st.error("This exit ticket is no longer active. Please contact your teacher.")
                        return
                    
                    # Check if student has already attempted this ticket
                    if check_student_already_attempted(db, ticket_id, student_name):
                        st.error(f"❌ You have already completed this exit ticket!")
                        st.info("Each student can attempt an exit ticket only once.")
                        return
                    
                    # Store ticket data and student name in session state
                    st.session_state.ticket_data = ticket_data
                    st.session_state.student_name = student_name
                    st.session_state.ticket_current_question = 0
                    st.session_state.ticket_user_answers = {}
                    st.session_state.ticket_quiz_completed = False
                    st.session_state.ticket_show_feedback = False
                    st.session_state.ticket_last_user_answer = None
                    st.session_state.response_saved = False
                    st.session_state.student_already_attempted = False
                    
                    st.rerun()
                else:
                    st.error("Invalid ticket code. Please check and try again.")

def show_ticket_quiz_page():
    """Display the exit ticket quiz interface"""
    ticket_data = st.session_state.ticket_data
    questions = ticket_data['questions']
    current_q = st.session_state.ticket_current_question

    # Initialize flags in session state if not exists
    if 'ticket_question_flags' not in st.session_state:
        st.session_state.ticket_question_flags = {}

    # Display ticket info
    st.header(f"🎫 {ticket_data.get('title', 'Exit Ticket')}")
    
    # Display student and ticket info
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Subject:** {ticket_data.get('subject', 'N/A')}")
        st.markdown(f"**Teacher:** {ticket_data.get('teacher_name', 'N/A')}")
    with col2:
        st.markdown(f"**Student:** {st.session_state.get('student_name', 'Unknown')}")
        st.markdown(f"**Ticket Code:** {ticket_data.get('ticket_id', 'N/A')}")
    
    st.markdown("---")

    if current_q >= len(questions):
        st.session_state.ticket_quiz_completed = True
        st.rerun()
        return

    # Progress bar
    progress = (current_q + 1) / len(questions)
    st.progress(progress)
    st.caption(f"Question {current_q + 1} of {len(questions)}")

    question_data = questions[current_q]
    st.subheader(f"Question {current_q + 1}")
    st.markdown(f"**{question_data['question']}**")

    # Flag button section
    col1, col2 = st.columns([3, 1])
    with col2:
        is_flagged = st.session_state.ticket_question_flags.get(current_q, False)
        flag_text = "🚩 Flagged" if is_flagged else "🏳️ Flag Question"
        flag_color = "secondary" if is_flagged else "primary"
        
        if st.button(flag_text, key=f"flag_btn_{current_q}", type=flag_color):
            # Toggle flag status
            st.session_state.ticket_question_flags[current_q] = not is_flagged
            if not is_flagged:
                st.warning("⚠️ Question flagged! This indicates you find the question unclear or out of syllabus.")
            else:
                st.success("✅ Flag removed from this question.")
            st.rerun()

    # Show flag status
    if is_flagged:
        st.warning("🚩 **This question is flagged** - You've marked this as unclear or potentially out of syllabus.")

    # Show answer options in a form - MAINTAIN ORIGINAL ORDER
    with st.form(f"ticket_question_{current_q}"):
        answer_given = current_q in st.session_state.ticket_user_answers

        # Keep options in A, B, C, D order - no randomization
        option_keys = ['A', 'B', 'C', 'D']  # Fixed order
        available_options = [key for key in option_keys if key in question_data['options']]
        
        user_answer = st.radio(
            "Select your answer:",
            options=available_options,  # Use fixed order
            format_func=lambda x: f"{x}) {question_data['options'][x]}",
            key=f"ticket_radio_{current_q}",
            disabled=answer_given
        )

        submitted = st.form_submit_button("Submit Answer", type="primary", disabled=answer_given)

    # Process after form is submitted (outside form block)
    if submitted:
        st.session_state.ticket_user_answers[current_q] = user_answer
        st.session_state.ticket_last_user_answer = user_answer

        correct_answer = question_data['correct_answer']
        if user_answer == correct_answer:
            st.success("✅ Correct!")
        else:
            st.error(f"❌ Incorrect. The correct answer is {correct_answer})")

        st.info(f"**Explanation:** {question_data.get('explanation', 'No explanation provided.')}")

    # Flag information box
    with st.expander("ℹ️ What does flagging a question mean?"):
        st.markdown("""
        **Flag a question if:**
        - The question is unclear or confusing
        - The question seems to be out of syllabus
        - You think there might be an error in the question
        - The concept wasn't covered in class
        
        Your teacher will be able to see which questions were flagged and can review them.
        """)

    # Navigation buttons (outside the form)
    col1, col2 = st.columns([1, 1])

    with col1:
        if current_q > 0:
            if st.button("⬅️ Previous Question", key=f"ticket_prev_{current_q}"):
                st.session_state.ticket_current_question = current_q - 1
                st.rerun()

    with col2:
        if current_q < len(questions) - 1:
            if st.button("➡️ Next Question", key=f"ticket_next_{current_q}"):
                st.session_state.ticket_current_question = current_q + 1
                st.rerun()
        else:
            if st.button("🏁 Finish Exit Ticket", key=f"ticket_finish_{current_q}"):
                st.session_state.ticket_quiz_completed = True
                st.rerun()

def show_ticket_results_page():
    """Display results after completing the exit ticket"""
    ticket_data = st.session_state.ticket_data
    questions = ticket_data['questions']
    user_answers = st.session_state.ticket_user_answers
    question_flags = st.session_state.get('ticket_question_flags', {})
    
    st.header("🎉 Exit Ticket Completed!")
    
    # Display ticket and student info
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Subject:** {ticket_data.get('subject', 'N/A')}")
        st.markdown(f"**Teacher:** {ticket_data.get('teacher_name', 'N/A')}")
    with col2:
        st.markdown(f"**Student:** {st.session_state.get('student_name', 'Unknown')}")
        st.markdown(f"**Ticket Code:** {ticket_data.get('ticket_id', 'N/A')}")
    
    st.markdown("---")
    
    # Calculate score
    correct_count = 0
    total_questions = len(questions)
    
    for i, question_data in enumerate(questions):
        if i in user_answers and user_answers[i] == question_data['correct_answer']:
            correct_count += 1
    
    score_percentage = (correct_count / total_questions) * 100
    
    # Display score with styling
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.metric(
            label="📊 Your Score",
            value=f"{correct_count}/{total_questions}",
            delta=f"{score_percentage:.1f}%"
        )
    
    # Show flagged questions summary
    flagged_count = len([q for q in question_flags.values() if q])
    if flagged_count > 0:
        st.warning(f"🚩 You flagged {flagged_count} question(s) as unclear or out of syllabus.")

    # Save student response to Firebase (only once and with better error handling)
    if 'response_saved' not in st.session_state or not st.session_state.response_saved:
        score_data = {
            "correct_count": correct_count,
            "total_questions": total_questions,
            "percentage": score_percentage
        }
        
        try:
            from firebase_helper import save_student_response
            with st.spinner("💾 Saving your response..."):
                success = save_student_response(
                    db, 
                    ticket_data['ticket_id'], 
                    st.session_state.get('student_name', 'Unknown'),
                    user_answers,
                    score_data,
                    question_flags  # Pass flags to save function
                )
                
                if success:
                    st.session_state.response_saved = True
                    st.success("✅ Your response has been recorded!")
                else:
                    st.error("❌ You have already completed this exit ticket!")
                    st.info("Each student can attempt an exit ticket only once.")
                    
        except Exception as e:
            st.error(f"❌ Failed to save your response: {str(e)}")
            st.info("Please contact your teacher if this problem persists.")
            print(f"Error saving response: {e}")
    else:
        st.info("✅ Response already saved!")
    
    # Performance message
    if score_percentage >= 80:
        st.success("🌟 Excellent work! You have a strong understanding of the concepts.")
    elif score_percentage >= 60:
        st.info("👍 Good job! You understand most concepts well.")
    else:
        st.warning("📚 Keep studying! Review the concepts and try again.")
    
    st.markdown("---")
    
    # Detailed review - MAINTAIN ORIGINAL ORDER
    st.subheader("📝 Detailed Review")
    
    for i, question_data in enumerate(questions):
        flag_status = " 🚩" if question_flags.get(i, False) else ""
        with st.expander(f"Question {i + 1}: {question_data['question'][:50]}...{flag_status}"):
            st.markdown(f"**Question:** {question_data['question']}")
            
            # Show flag status
            if question_flags.get(i, False):
                st.warning("🚩 **You flagged this question** as unclear or out of syllabus")
            
            user_answer = user_answers.get(i, "NA")
            correct_answer = question_data['correct_answer']
            
            # Show all options in A, B, C, D order
            st.markdown("**All Options:**")
            option_keys = ['A', 'B', 'C', 'D']
            for opt_key in option_keys:
                if opt_key in question_data['options']:
                    option_text = question_data['options'][opt_key]
                    if opt_key == user_answer and opt_key == correct_answer:
                        st.success(f"✅ {opt_key}) {option_text} (Your answer - Correct)")
                    elif opt_key == user_answer:
                        st.error(f"❌ {opt_key}) {option_text} (Your answer - Incorrect)")
                    elif opt_key == correct_answer:
                        st.success(f"✅ {opt_key}) {option_text} (Correct answer)")
                    else:
                        st.markdown(f"{opt_key}) {option_text}")
            
            st.info(f"**Explanation:** {question_data.get('explanation', 'No explanation provided.')}")
            st.markdown(f"**Topic:** {question_data.get('topic', 'Unknown')}")
            st.markdown(f"**Subtopic:** {question_data.get('subtopic', 'Unknown')}")
    
    # Action buttons
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("🔄 Take Another Exit Ticket"):
            # Reset ticket session state
            st.session_state.ticket_data = None
            st.session_state.ticket_current_question = 0
            st.session_state.ticket_user_answers = {}
            st.session_state.ticket_quiz_completed = False
            st.session_state.ticket_show_feedback = False
            st.session_state.ticket_last_user_answer = None
            st.session_state.student_name = None
            st.session_state.response_saved = False
            st.session_state.student_already_attempted = False
            st.session_state.ticket_question_flags = {}  # Reset flags
            if 'ticket_initialized' in st.session_state:
                del st.session_state.ticket_initialized
            st.rerun()

    with col2:
        st.markdown("**Need help?**")
        st.markdown("Contact your teacher if you have any questions.")

if __name__ == "__main__":
    main()