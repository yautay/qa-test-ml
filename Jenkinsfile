// Jenkinsfile — Perceptual Metrics Service
// Declarative pipeline running inside a Python 3.12 Docker container.
// Docs: https://www.jenkins.io/doc/book/pipeline/syntax/

pipeline {
    agent {
        docker {
            image 'python:3.12-slim'
            args '--user root'
        }
    }

    options {
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
        disableConcurrentBuilds()
    }

    environment {
        PIP_CACHE_DIR        = "${WORKSPACE}/.cache/pip"
        CELERY_TASK_ALWAYS_EAGER = 'true'
        JOB_STORE_BACKEND    = 'memory'
    }

    stages {
        stage('Install') {
            steps {
                sh '''
                    pip install --upgrade pip
                    pip install -r requirements-dev.txt
                '''
            }
        }

        stage('Test') {
            steps {
                sh '''
                    pytest -q \
                        --cov=app \
                        --cov-report=term-missing \
                        --cov-report=xml:coverage.xml \
                        --junitxml=pytest-results.xml
                '''
            }
            post {
                always {
                    junit 'pytest-results.xml'
                }
            }
        }

        stage('Lint') {
            parallel {
                stage('ruff') {
                    steps {
                        sh 'ruff check .'
                    }
                }
                stage('black') {
                    steps {
                        sh 'black --check .'
                    }
                }
                stage('mypy') {
                    steps {
                        sh 'mypy .'
                    }
                }
            }
        }

        stage('Security') {
            parallel {
                stage('pip-audit') {
                    steps {
                        sh 'pip-audit'
                    }
                }
                stage('bandit') {
                    steps {
                        sh '''
                            bandit -r app/ -ll -f json -o bandit-report.json || true
                            bandit -r app/ -ll
                        '''
                    }
                    post {
                        always {
                            archiveArtifacts artifacts: 'bandit-report.json', allowEmptyArchive: true
                        }
                    }
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'coverage.xml, pytest-results.xml', allowEmptyArchive: true
            cleanWs()
        }
        success {
            echo "Pipeline passed — all checks green."
        }
        failure {
            echo "Pipeline failed — check the stage logs above."
        }
    }
}
