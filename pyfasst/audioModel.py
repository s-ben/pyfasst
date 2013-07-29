"""AudioModel: 

Description
-----------

FASST (Flexible Audio Source Separation Toolbox) class
    subclass it to obtain your own flavoured source separation model!

Usage
-----

TBD

Reference
---------

    A. Ozerov, E. Vincent and F. Bimbot
    \"A General Flexible Framework for the Handling of Prior Information
    in Audio Source Separation,\" 
    IEEE Transactions on Audio, Speech and Signal Processing 20(4),
    pp. 1118-1133 (2012)                            
    Available: `Archive on HAL <http://hal.inria.fr/hal-00626962/>`_
    
    Adapted from the Matlab toolbox available at
    http://bass-db.gforge.inria.fr/fasst/

Copyright (TBD)
---------------

Jean-Louis Durrieu, EPFL-SSTI-IEL-LTS5
::

    jean DASH louis AT durrieu DOT ch

2012-2013

Reference
---------

"""

import numpy as np 
import audioObject as ao
import warnings, os

import tools.signalTools as st
from SeparateLeadStereo import SeparateLeadStereoTF as SLS
import demixTF as demix
import tftransforms.tft as tft # loads the possible transforms

tftransforms = {
    'stftold': tft.TFTransform, # just making dummy, in FASST, not used
    'stft': tft.STFT,
    'mqt': tft.MinQTransfo,
    'minqt': tft.MinQTransfo,
    'nsgmqt': tft.NSGMinQT,
    'cqt': tft.CQTransfo}

eps = 1e-10
log_prior_small_cst = 1e-70
soundCelerity = 340. # m/s

########## Useful functions ##########

def NMF_decomposition(SX, nbComps=10, niter=10, verbose=0):
    """NMF multiplicative gradient, for Itakura Saito
    divergence measure between SX and `np.dot(W,H)`
    """
    freqs, nframes = SX.shape
    W = np.random.randn(freqs, nbComps)**2
    H = np.random.randn(nbComps, nframes)**2
    W /= W.sum(axis=0)
    
    for i in range(niter):
        if verbose:
            print "    NMF iteration %d out of %d" %(i+1, niter)
        # updating W
        hatSX = np.dot(W, H)
        num = np.dot(SX / np.maximum(hatSX**2, eps),
                     H.T)
        den = np.dot(1 / np.maximum(hatSX, eps),
                     H.T)
        
        W *= num / np.maximum(den, eps)
        
        sumW = W.sum(axis=0)
        sumW[sumW==0] = 1.
        W /= sumW
        H *= np.vstack(sumW)
        
        # updating H
        hatSX = np.dot(W, H)
        num = np.dot(W.T,
                     SX / np.maximum(hatSX**2, eps))
        den = np.dot(W.T,
                     1 / np.maximum(hatSX, eps))
        
        H *= num / np.maximum(den, eps)
    
    return W, H

def NMF_decomp_init(SX, nbComps=10, niter=10, verbose=0,
                    Winit=None, Hinit=None,
                    updateW=True, updateH=True):
    """NMF multiplicative gradient, for Itakura Saito
    divergence measure between SX and np.dot(W,H)
    """
    freqs, nframes = SX.shape
    if Winit is None or (Winit.shape != (freqs, nbComps)):
        W = np.random.randn(freqs, nbComps)**2
        if verbose and not updateW:
            print "    NMF decomp init: not updating randomly initialized W..."
    else:
        W = np.copy(Winit)
        if verbose and updateW:
            print "    NMF decomp init: updating provided initial W..." 
            
    if Hinit.shape == (nbComps, nframes):
        H = np.copy(Hinit.T)
        if verbose and updateH:
            print "    NMF decomp init: updating provided initial H..."
    elif  Hinit.shape == (nframes, nbComps):
        H = np.copy(Hinit)
        if verbose and updateH:
            print "    NMF decomp init: updating provided initial H..."
    else:
        H = np.random.randn(nframes, nbComps, )**2
        if verbose and not updateH:
            print "    NMF decomp init: not updating randomly initialized H..."
    
    if updateW:
        W /= W.sum(axis=0)
    
    for i in range(niter):
        if verbose:
            print "    NMF iteration %d out of %d" %(i+1, niter)
        if updateW:# updating W
            hatSX = np.dot(W, H.T)
            num = np.dot(SX / np.maximum(hatSX**2, eps),
                         H)
            den = np.dot(1 / np.maximum(hatSX, eps),
                         H)
            
            W *= num / np.maximum(den, eps)
            
            sumW = W.sum(axis=0)
            sumW[sumW==0] = 1.
            W /= sumW
            H *= sumW
        
        if updateH:# updating H
            hatSX = np.dot(H, W.T)
            num = np.dot(SX.T / np.maximum(hatSX**2, eps),
                         W)
            den = np.dot(1 / np.maximum(hatSX, eps),
                         W)
            
            H *= num / np.maximum(den, eps)
    
    return W, H.T

def SFNMF_decomp_init(SX, nbComps=10, nbFiltComps=10,
                      niter=10, verbose=0,
                      Winit=None, Hinit=None,
                      WFiltInit=None, HFiltInit=None,
                      updateW=True, updateH=True,
                      updateWFilt=True, updateHFilt=True,
                      nbResComps=2):
    """Implements a simple source/filter NMF algorithm
    """
    freqs, nframes = SX.shape
    if Winit is None or (Winit.shape != (freqs, nbComps)):
        W = np.random.randn(freqs, nbComps)**2
        if verbose and not updateW:
            print "    NMF decomp init: not updating randomly initialized W..."
    else:
        W = np.copy(Winit)
        if verbose and updateW:
            print "    NMF decomp init: updating provided initial W..." 
    if Hinit is None or (Hinit.shape != (nframes, nbComps)):
        H = np.random.randn(nframes, nbComps, )**2
        if verbose and not updateH:
            print "    NMF decomp init: not updating randomly initialized H..."
    else:
        H = np.copy(Hinit)
        if verbose and updateH:
            print "    NMF decomp init: updating provided initial H..."
    
    if updateW:
        W /= W.sum(axis=0)
    
    if WFiltInit is None or (WFiltInit.shape != (freqs, nbFiltComps)):
        WFilt = np.random.randn(freqs, nbFiltComps)**2
        if verbose and not updateWFilt:
            print "    NMF decomp init: not "+\
                  "updating randomly initialized WFilt..."
    else:
        WFilt = np.copy(WFiltInit)
        if verbose and updateWFilt:
            print "    NMF decomp init: updating provided initial WFilt..." 
    if HFiltInit is None or (HFiltInit.shape != (nframes, nbFiltComps)):
        HFilt = np.random.randn(nframes, nbFiltComps, )**2
        if verbose and not updateHFilt:
            print "    NMF decomp init: not updating "+\
                  "randomly initialized HFilt..."
    else:
        HFilt = np.copy(HFiltInit)
        if verbose and updateHFilt:
            print "    NMF decomp init: updating provided initial H..."
    
    if updateWFilt:
        WFilt /= WFilt.sum(axis=0)
    
    Wres = (1 + np.random.randn(freqs, nbResComps))**2
    Hres = (1 + np.random.randn(nframes, nbResComps))**2
    
    if verbose>1:
        import matplotlib.pyplot as plt
        fig = plt.figure()
        ax = fig.add_subplot(211)
        im = ax.imshow(SX)
        fig.colorbar(im)
        ax2 = fig.add_subplot(212, sharex=ax)
        im2 = ax2.imshow(SX)
        fig.colorbar(im2)
    
    for i in range(niter):
        if verbose:
            print "    NMF iteration %d out of %d" %(i+1, niter)
        if updateW:# updating W
            if verbose:
                print "        updating w f0"
            SF0 = np.dot(W, H.T)
            SPHI = np.dot(WFilt, HFilt.T)
            Sres = np.dot(Wres, Hres.T)
            hatSX = SF0 * SPHI + Sres
            num = np.dot(SX * SPHI/ np.maximum(hatSX ** 2, eps),
                         H)
            den = np.dot(SPHI / np.maximum(hatSX, eps),
                         H)
            
            W *= num / np.maximum(den, eps)
            
            sumW = W.sum(axis=0)
            sumW[sumW==0] = 1.
            W /= sumW
            H *= sumW
        
        if updateH:# updating H
            if verbose:
                print "        updating h f0"
            SF0 = np.dot(H, W.T)
            SPHI = np.dot(HFilt, WFilt.T)
            Sres = np.dot(Hres, Wres.T)
            hatSX = SF0 * SPHI + Sres
            num = np.dot(SX.T * SPHI/ np.maximum(hatSX ** 2, eps),
                         W)
            den = np.dot(SPHI / np.maximum(hatSX, eps),
                         W)
            
            H *= num / np.maximum(den, eps)
            if verbose>1:
                im.set_data(np.log(hatSX.T))
                im.set_clim([im.get_array().min(),
                             im.get_array().max()])
                plt.draw()
            
        if updateWFilt:# updating WFilt
            if verbose:
                print "        updating w filter"
            SF0 = np.dot(W, H.T)
            SPHI = np.dot(WFilt, HFilt.T)
            Sres = np.dot(Wres, Hres.T)
            hatSX = SF0 * SPHI + Sres
            num = np.dot(SX * SF0 / np.maximum(hatSX ** 2, eps),
                         HFilt)
            den = np.dot(SF0 / np.maximum(hatSX, eps),
                         HFilt)
            
            WFilt *= num / np.maximum(den, eps)
            
            # normalization of Wfilt
            sumW = WFilt.sum(axis=0)
            sumW[sumW==0] = 1.
            WFilt /= sumW
            HFilt *= sumW
            # normalizing Hfilt and sending energy to H
            ##sumH = HFilt.sum(axis=1)
            ##HFilt /= np.vstack(sumH)
            ##H *= np.vstack(sumH)
        
        if updateHFilt:# updating HFilt
            if verbose:
                print "        updating h filter"
            SF0 = np.dot(H, W.T)
            SPHI = np.dot(HFilt, WFilt.T)
            Sres = np.dot(Hres, Wres.T)
            hatSX = SF0 * SPHI + Sres
            
            if verbose>1:
                im2.set_data(np.log(hatSX.T))
                im2.set_clim([im2.get_array().min(),
                              im2.get_array().max()])
                plt.draw()
                
            num = np.dot(SX.T * SF0 / np.maximum(hatSX ** 2, eps),
                         WFilt)
            den = np.dot(SF0 / np.maximum(hatSX, eps),
                         WFilt)
            
            HFilt *= num / np.maximum(den, eps)
            
            # normalizing Hfilt and sending energy to H
            sumH = HFilt.sum(axis=1)
            H *= np.vstack(sumH)
            sumH[sumH==0] = 1.
            HFilt /= np.vstack(sumH)
            
            ##if verbose>1:
            ##    im2.set_data(np.log(HFilt.T))
            ##    im2.set_clim([im2.get_array().min(),
            ##                  im2.get_array().max()])
            ##    plt.draw()
        # update residual comps:
        if verbose:
            print "        updating w residual"
        SF0 = np.dot(W, H.T)
        SPHI = np.dot(WFilt, HFilt.T)
        Sres = np.dot(Wres, Hres.T)
        hatSX = SF0 * SPHI + Sres
        num = np.dot(SX / np.maximum(hatSX ** 2, eps),
                     Hres)
        den = np.dot(1 / np.maximum(hatSX, eps),
                     Hres)
        
        Wres *= num / np.maximum(den, eps)
        
        # normalization of Wfilt
        sumW = Wres.sum(axis=0)
        sumW[sumW==0] = 1.
        Wres /= sumW
        Hres *= sumW
        
        if verbose:
            print "        updating h residual"
        SF0 = np.dot(H, W.T)
        SPHI = np.dot(HFilt, WFilt.T)
        Sres = np.dot(Hres, Wres.T)
        hatSX = SF0 * SPHI + Sres
            
        num = np.dot(SX.T  / np.maximum(hatSX ** 2, eps),
                     Wres)
        den = np.dot(1 / np.maximum(hatSX, eps),
                     Wres)
        
        Hres *= num / np.maximum(den, eps)
    
    return W, H.T, WFilt, HFilt.T, Wres, Hres
    

def inv_mat(mat_diag, mat_off):
    """invert hermitian matrix
    """
    det_mat = np.prod(mat_diag, axis=0) - np.abs(mat_off)**2
    det_mat = (
        np.sign(det_mat) *
        np.maximum(np.abs(det_mat), eps)
        )
    
    inv_mat_diag = np.zeros_like(mat_diag)
    inv_mat_diag[0] = mat_diag[1] / det_mat
    inv_mat_diag[1] = mat_diag[0] / det_mat
    inv_mat_off = - mat_off / det_mat
    
    return inv_mat_diag, inv_mat_off, det_mat

def gen_steer_vec_far_src_uniform_linear_array(freqs,
                                               nchannels,
                                               theta,
                                               distanceInterMic):
    """generate steering vector with relative far source,
    uniformly spaced sensor array
    
    **Description**:
    
    assuming the source is far (compared to the dimensions of the array)
    The sensor array is also assumed to be a linear array, the direction of
    arrival (DOA) theta is defined as in the following incredible ASCII
    art drawing::
    
          theta
        ----->/              /
        |    /              /
        y   /              /
           /              /
        ^ /              /
        |/              /
        +---> x
        o    o    o    o    o    o
        M1   M2   M3  ...
        <--->
          d = distanceInterMic
    
    That is more likely valid for electro-magnetic fields, for acoustic
    wave fields, one should probably take into account the difference of
    gain between the microphones (see ``gen_steer_vec_acous``)
    
    **Output**:
    
    a (nc, nfreqs) ndarray
        contains the steering vectors, one for each channel, and
    
    """
    a = np.exp(- 1j * 2. * np.pi *
               np.outer(np.arange(nchannels),
                        freqs) *
               (distanceInterMic / soundCelerity) * 
               np.sin(theta))
    return a

def gen_steer_vec_acous(freqs,
                        dist_src_mic):
    gains = 1 / (np.sqrt(4. * np.pi) * dist_src_mic)
    a = (np.vstack(gains) *
         np.exp(- 1j * 2. * np.pi *
                np.outer(dist_src_mic,
                         freqs) /
                soundCelerity
                )
         )
    return a

def dir_diag_stereo(Cx,
                    nft=2048,
                    ntheta=512,
                    samplerate=44100,#Hz
                    distanceInterMic=0.3,#m
                    ):
    """Compute the diagram of directivity for the input
    short time Fourier transform second order statistics in Cx
    
    .. math::
    
        C_x[0] = E[|x_0|^2]
        
        C_x[2] = E[|x_1|^2]
        
        C_x[1] = E[x_0 x_1^H]
        
    
    **Method**:
    
    We use the Capon method, on each of the Fourier channel:
    
        phi_k(theta) = a_k(theta).H inv(Rxx) a_k(theta)
    
    The algorithm therefore returns one directivity graph for each
    frequency band. 
    
    **Remarks**:
    
    One can compute a summary directivity by adding the directivity functions
    across all the frequency channels. The invert of the resulting array may
    also be of interest (looking at peaks and not valleys to find directions):
    
    >>> directivity_diag = dir_diag_stereo(Cx)
    >>> summary_dir_diag = 1./directivity_diag.sum(axis=1)
    
    Some tests show that it is very important that the distance between the
    microphone is known. Otherwise, little can be infered from the resulting
    directivity measure...
    """
    nchannels = 2 # this function only works for stereo audio
    
    # for capon, we need the average of Cx:
    meanCx_diag = np.array([Cx[0].mean(axis=1),
                            Cx[2].mean(axis=1)],
                           dtype=np.float64)
    meanCx_off  = Cx[1].mean(axis=1)
    # ... and its inverse:
    inv_mat_diag, inv_mat_off, det_mat = (
        inv_mat(meanCx_diag, meanCx_off)
        )
    
    if not np.all(det_mat):
        raise ValueError(
            "Not possible to compute directivity, singular covariance. "+
            "\nThe channels are probably either identical or colinear.")
    
    nfreqs = nft / 2 + 1
    freqs = np.arange(nfreqs) * 1. / nft * samplerate
    
    # now computing the directivity diagram, angle after angle
    directivity_diagram = np.zeros([ntheta, nfreqs], dtype=np.float64)
    # theta from -pi/2 to +pi/2
    theta = np.arange(1, ntheta+1) * np.pi / (ntheta + 1.) - np.pi / 2.
    for nth in range(ntheta):
        # Compute steering vectors for each frequency
        filt = gen_steer_vec_far_src_uniform_linear_array(freqs,
                                                          nchannels,
                                                          theta[nth],
                                                          distanceInterMic)
        
        directivity_diagram[nth] = (
            (np.abs(filt[0]**2)) * inv_mat_diag[0] +
            (np.abs(filt[1]**2)) * inv_mat_diag[1] +
            2. * np.real((np.conjugate(filt[0]) * filt[1]) *
                         inv_mat_off)
            #filt[0] * np.conjugate(filt[1]) * np.conjugate(inv_mat_off) +
            #np.conjugate(filt[0]) * filt[1] * inv_mat_off
            )
    
    return directivity_diagram, theta

# coming from sepLeadStereo programs
# (https://github.com/wslihgt/separateLeadStereo):
def generate_WF0_chirped(minF0, maxF0, Fs, Nfft=2048, stepNotes=4, \
                         lengthWindow=2048, Ot=0.5, perF0=2, \
                         depthChirpInSemiTone=0.5, loadWF0=True,
                         analysisWindow='hanning'):
    """
    ``F0Table, WF0 = generate_WF0_chirped(minF0, maxF0, Fs, Nfft=2048,
    stepNotes=4, lengthWindow=2048,
    Ot=0.5, perF0=2,
    depthChirpInSemiTone=0.5)``
    
    Generates a 'basis' matrix for the source part WF0, using the
    source model KLGLOTT88, with the following I/O arguments:
    
    **Inputs**:
    
    *    `minF0`:                the minimum value for the fundamental
                                 frequency (F0)
    *    `maxF0`:                the maximum value for F0
    *    Fs:                     the desired sampling rate
    *    Nfft:                   the number of bins to compute the Fourier
                                 transform
    *    stepNotes:              the number of F0 per semitone
    *    lengthWindow:           the size of the window for the Fourier
                                 transform
    *    Ot:                     the glottal opening coefficient for
                                 KLGLOTT88
    *    perF0:                  the number of chirps considered per F0
                                 value
    *    depthChirpInSemiTone:   the maximum value, in semitone, of the
                                 allowed chirp per F0
                             
    **Outputs**:
    
    *    F0Table:

                the vector containing the values of the fundamental
                frequencies in Hertz (Hz) corresponding to the
                harmonic combs in WF0, i.e. the columns of WF0
    *    WF0:
    
                the basis matrix, where each column is a harmonic comb
                generated by KLGLOTT88 (with a sinusoidal model, then
                transformed into the spectral domain)
                
    """
    
    # generating a filename to keep data:
    filename = str('').join(['wf0_',
                             '_minF0-', str(minF0),
                             '_maxF0-', str(maxF0),
                             '_Fs-', str(Fs),
                             '_Nfft-', str(Nfft),
                             '_stepNotes-', str(stepNotes),
                             '_Ot-', str(Ot),
                             '_perF0-', str(perF0),
                             '_depthChirp-', str(depthChirpInSemiTone),
                             '_analysisWindow-', analysisWindow,
                             '.npz'])
    
    if os.path.isfile(filename) and loadWF0:
        print "Reading WF0 and F0Table from stored arrays."
        struc = np.load(filename)
        return struc['F0Table'], struc['WF0']
    
    print "First time WF0 computed with these parameters, please wait..."
    # converting to double arrays:
    minF0=np.double(minF0)
    maxF0=np.double(maxF0)
    Fs=np.double(Fs)
    stepNotes=np.double(stepNotes)
    
    # computing the F0 table:
    numberOfF0 = np.ceil(12.0 * stepNotes * np.log2(maxF0 / minF0)) + 1
    F0Table=minF0 * (2 ** (np.arange(numberOfF0,dtype=np.double) \
                           / (12 * stepNotes)))
    
    numberElementsInWF0 = numberOfF0 * perF0
    
    # computing the desired WF0 matrix
    WF0 = np.zeros([Nfft, numberElementsInWF0],dtype=np.double)
    for fundamentalFrequency in np.arange(numberOfF0):
        odgd, odgdSpec = \
              generate_ODGD_spec(F0Table[fundamentalFrequency], Fs, \
                                 Ot=Ot, lengthOdgd=lengthWindow, \
                                 Nfft=Nfft, t0=0.0,\
                                 analysisWindowType=analysisWindow)
        WF0[:,fundamentalFrequency * perF0] = np.abs(odgdSpec) ** 2
        for chirpNumber in np.arange(perF0 - 1):
            F2 = F0Table[fundamentalFrequency] \
                 * (2 ** ((chirpNumber + 1.0) * depthChirpInSemiTone \
                          / (12.0 * (perF0 - 1.0))))
            # F0 is the mean of F1 and F2.
            F1 = 2.0 * F0Table[fundamentalFrequency] - F2 
            odgd, odgdSpec = \
                  generate_ODGD_spec_chirped(F1, F2, Fs, \
                                             Ot=Ot, \
                                             lengthOdgd=lengthWindow, \
                                             Nfft=Nfft, t0=0.0)
            WF0[:,fundamentalFrequency * perF0 + chirpNumber + 1] = \
                                       np.abs(odgdSpec) ** 2
    
    np.savez(filename, F0Table=F0Table, WF0=WF0)
    
    return F0Table, WF0

def generate_ODGD_spec(F0, Fs, lengthOdgd=2048, Nfft=2048, Ot=0.5, \
                       t0=0.0, analysisWindowType='sinebell'): 
    """
    generateODGDspec:
    
    generates a waveform ODGD and the corresponding spectrum,
    using as analysis window the -optional- window given as
    argument.
    """
    
    # converting input to double:
    F0 = np.double(F0)
    Fs = np.double(Fs)
    Ot = np.double(Ot)
    t0 = np.double(t0)
    
    # compute analysis window of given type:
    if analysisWindowType=='sinebell':
        analysisWindow = ao.sinebell(lengthOdgd)
    else:
        if analysisWindowType=='hanning' or \
               analysisWindowType=='hanning':
            analysisWindow = np.hanning(lengthOdgd)
    
    # maximum number of partials in the spectral comb:
    partialMax = np.floor((Fs / 2) / F0)
    
    # Frequency numbers of the partials:
    frequency_numbers = np.arange(1,partialMax + 1)
    
    # intermediate value
    temp_array = 1j * 2.0 * np.pi * frequency_numbers * Ot
    
    # compute the amplitudes for each of the frequency peaks:
    amplitudes = F0 * 27 / 4 \
                 * (np.exp(-temp_array) \
                    + (2 * (1 + 2 * np.exp(-temp_array)) / temp_array) \
                    - (6 * (1 - np.exp(-temp_array)) \
                       / (temp_array ** 2))) \
                       / temp_array
    
    # Time stamps for the time domain ODGD
    timeStamps = np.arange(lengthOdgd) / Fs + t0 / F0
    
    # Time domain odgd:
    odgd = np.exp(np.outer(2.0 * 1j * np.pi * F0 * frequency_numbers, \
                           timeStamps)) \
                           * np.outer(amplitudes, np.ones(lengthOdgd))
    odgd = np.sum(odgd, axis=0)
    
    # spectrum:
    odgdSpectrum = np.fft.fft(np.real(odgd * analysisWindow), n=Nfft)
    
    return odgd, odgdSpectrum

def generate_ODGD_spec_chirped(F1, F2, Fs, lengthOdgd=2048, Nfft=2048, \
                               Ot=0.5, t0=0.0, \
                               analysisWindowType='sinebell'):
    """
    generateODGDspecChirped:
    
    generates a waveform ODGD and the corresponding spectrum,
    using as analysis window the -optional- window given as
    argument.
    """
    
    # converting input to double:
    F1 = np.double(F1)
    F2 = np.double(F2)
    F0 = np.double(F1 + F2) / 2.0
    Fs = np.double(Fs)
    Ot = np.double(Ot)
    t0 = np.double(t0)
    
    # compute analysis window of given type:
    if analysisWindowType == 'sinebell':
        analysisWindow = ao.sinebell(lengthOdgd)
    else:
        if analysisWindowType == 'hanning' or \
               analysisWindowType == 'hann':
            analysisWindow = np.hanning(lengthOdgd)
    
    # maximum number of partials in the spectral comb:
    partialMax = np.floor((Fs / 2) / np.maximum(F1, F2))
    
    # Frequency numbers of the partials:
    frequency_numbers = np.arange(1,partialMax + 1)
    
    # intermediate value
    temp_array = 1j * 2.0 * np.pi * frequency_numbers * Ot
    
    # compute the amplitudes for each of the frequency peaks:
    amplitudes = F0 * 27 / 4 * \
                 (np.exp(-temp_array) \
                  + (2 * (1 + 2 * np.exp(-temp_array)) / temp_array) \
                  - (6 * (1 - np.exp(-temp_array)) \
                     / (temp_array ** 2))) \
                  / temp_array
    
    # Time stamps for the time domain ODGD
    timeStamps = np.arange(lengthOdgd) / Fs + t0 / F0
    
    # Time domain odgd:
    odgd = np.exp(2.0 * 1j * np.pi \
                  * (np.outer(F1 * frequency_numbers,timeStamps) \
                     + np.outer((F2 - F1) \
                                * frequency_numbers,timeStamps ** 2) \
                     / (2 * lengthOdgd / Fs))) \
                     * np.outer(amplitudes,np.ones(lengthOdgd))
    odgd = np.sum(odgd,axis=0)
    
    # spectrum:
    odgdSpectrum = np.fft.fft(np.real(odgd * analysisWindow), n=Nfft)
    
    return odgd, odgdSpectrum

########## Filter generation functions   ##########

def generateHannBasis(numberFrequencyBins, sizeOfFourier, Fs, \
                      frequencyScale='linear', numberOfBasis=20, \
                      overlap=.75):
    isScaleRecognized = False
    if frequencyScale == 'linear':
        # number of windows generated:
        numberOfWindowsForUnit = np.ceil(1.0 / (1.0 - overlap))
        # recomputing the overlap to exactly fit the entire
        # number of windows:
        overlap = 1.0 - 1.0 / np.double(numberOfWindowsForUnit)
        # length of the sine window - that is also to say: bandwidth
        # of the sine window:
        lengthSineWindow = np.ceil(numberFrequencyBins \
                                   / ((1.0 - overlap) \
                                      * (numberOfBasis - 1) + 1 \
                                      - 2.0 * overlap))
        # even window length, for convenience:
        lengthSineWindow = 2.0 * np.floor(lengthSineWindow / 2.0) 
        
        # for later compatibility with other frequency scales:
        mappingFrequency = np.arange(numberFrequencyBins) 
        
        # size of the "big" window
        sizeBigWindow = 2.0 * numberFrequencyBins
        
        # centers for each window
        ## the first window is centered at, in number of window:
        firstWindowCenter = - numberOfWindowsForUnit + 1
        ## and the last is at
        lastWindowCenter = numberOfBasis - numberOfWindowsForUnit + 1
        ## center positions in number of frequency bins
        sineCenters = np.round(\
            np.arange(firstWindowCenter, lastWindowCenter) \
            * (1 - overlap) * np.double(lengthSineWindow) \
            + lengthSineWindow / 2.0)
        
        # For future purpose: to use different frequency scales
        isScaleRecognized = True
        
    # For frequency scale in logarithm (such as ERB scales) 
    if frequencyScale == 'log':
        isScaleRecognized = False
        
    # checking whether the required scale is recognized
    if not(isScaleRecognized):
        raise NotImplementedError("The desired feature for frequencyScale " + \
                                  "is not recognized yet...")
    
    # the shape of one window:
    prototypeSineWindow = np.hanning(lengthSineWindow)
    # adding zeroes on both sides, such that we do not need to check
    # for boundaries
    bigWindow = np.zeros([sizeBigWindow * 2, 1])
    bigWindow[(sizeBigWindow - lengthSineWindow / 2.0):\
              (sizeBigWindow + lengthSineWindow / 2.0)] \
              = np.vstack(prototypeSineWindow)
    
    WGAMMA = np.zeros([numberFrequencyBins, numberOfBasis])
    
    for p in np.arange(numberOfBasis):
        WGAMMA[:, p] = np.hstack(bigWindow[np.int32(mappingFrequency \
                                                    - sineCenters[p] \
                                                    + sizeBigWindow)])
        
    return WGAMMA


########## Main classes for audio models ##########

class FASST(object):
    """**FASST audio model**, from::
    
     A. Ozerov, E. Vincent and F. Bimbot
     \"A General Flexible Framework for the Handling of Prior Information
     in Audio Source Separation,\"  
     IEEE Transactions on Audio, Speech and Signal Processing 20(4),
     pp. 1118-1133 (2012)                            
     Available online: http://hal.inria.fr/hal-00626962/
    
    Adapted from the Matlab toolbox available at
    http://bass-db.gforge.inria.fr/fasst/
    """
    # for now only stft:
    implemented_transf = ['stft','stftold', 'mqt', 'minqt', 'cqt']
    implemented_annealing = ['ann', 'no_ann', ]
    
    def __init__(self,
                 audio,
                 transf='stft',
                 wlen=2048,
                 hopsize=512,
                 iter_num=50,
                 sim_ann_opt='ann',
                 ann_PSD_lim=[None, None],
                 verbose=0,
                 nmfUpdateCoeff=1.,
                 tffmin=25,
                 tffmax=18000,
                 tfWinFunc=None,
                 tfbpo=48,
                 lambdaCorr=0.):
        """**FASST**: Flexible Audio Source Separation Toolbox
        
        This is the superclass that implements the core functions for
        the framework for audio source separation as introduced in
            A. Ozerov, E. Vincent and F. Bimbot
            \"A General Flexible Framework for the Handling of Prior
            Information in Audio Source Separation,\" 
            IEEE Transactions on Audio, Speech and Signal Processing 20(4),
            pp. 1118-1133 (2012)                            
            Available: http://hal.inria.fr/hal-00626962/
        
        In order to use it, one should sub-class this class, and in particular
        define several elements that are assumed by the core functions for
        estimation and separation in this class, namely:
        
        **ATTRIBUTES** (WIP)
        spat_comps
        
        spec_comps
        
        audioObject
            samplerate
            channels
            
        sig_repr_params
            'transf'
            'wlen'
            'fsize'
            'hopsize'
            
        
        **ARGUMENT**
        
        """
        
        self.verbose = verbose
        self.nmfUpdateCoeff = nmfUpdateCoeff
        
        if isinstance(audio, ao.AudioObject):
            self.audioObject = audio
        elif isinstance(audio, str) or isinstance(audio, unicode):
            self.audioObject = ao.AudioObject(filename=audio)
        else:
            raise AttributeError("The provided audio parameter is"+
                                 "not a supported format.")
        
        # parameters to compute the signal representation:
        self.sig_repr_params = {}
        self.sig_repr_params['transf'] = transf.lower()  # transformation type
        self.sig_repr_params['wlen'] = ao.nextpow2(wlen)      # window length
        self.sig_repr_params['fsize'] = ao.nextpow2(wlen) # Fourier length
        self.sig_repr_params['hopsize'] = hopsize
        self.sig_repr_params['tffmin'] = tffmin
        self.sig_repr_params['tffmax'] = tffmax
        self.sig_repr_params['tfbpo'] = tfbpo
        self.sig_repr_params['tfWinFunc'] = tfWinFunc
        self.sig_repr_params['hopfactor'] = (
            1. * hopsize / self.sig_repr_params['wlen'])
        if self.sig_repr_params['transf'] not in self.implemented_transf \
               or self.sig_repr_params['transf'] not in tftransforms:
            raise NotImplementedError(self.sig_repr_params['transf']
                                      + " not yet implemented.")
        elif self.sig_repr_params['transf'] != 'stftold':
            self.tft = tftransforms[self.sig_repr_params['transf']](
                fmin=tffmin,
                fmax=tffmax,
                bins=tfbpo,
                fs=self.audioObject.samplerate,
                perfRast=1,
                linFTLen=self.sig_repr_params['fsize'],
                atomHopFactor=self.sig_repr_params['hopfactor'],
                )
        elif self.sig_repr_params['transf'] == 'stftold':
            self.tft = tftransforms['stft'](
                fmin=tffmin,
                fmax=tffmax,
                bins=tfbpo,
                fs=self.audioObject.samplerate,
                perfRast=1,
                linFTLen=self.sig_repr_params['fsize'],
                atomHopFactor=self.sig_repr_params['hopfactor'],
                )
            
            
        # demix parameters:
        self.demixParams = {
            'tffmin': tffmin, 'tffmax': tffmax,
            'tfbpo': tfbpo,
            'tfrepresentation': transf.lower(), # 'stft', #transf.lower()
            'wlen': self.sig_repr_params['wlen'],
            'hopsize': self.sig_repr_params['wlen']/2,
            'neighbors': 20,
            'winFunc': tfWinFunc,
            }
        
        # noise parameters
        self.noise = {}
        self.noise['PSD'] = np.zeros(self.sig_repr_params['fsize']/2+1)
        self.noise['sim_ann_opt'] = sim_ann_opt
        self.noise['ann_PSD_lim'] = ann_PSD_lim
        
        self.spat_comps = {}
        self.spec_comps = {}
        
        self.iter_num = iter_num
        self.lambdaCorr = lambdaCorr
    
    def comp_transf_Cx(self):
        """Computes the signal representation, according
        to the provided signal_representation flag
        """
        if not hasattr(self.audioObject, '_data'):
            self.audioObject._read()
        
        if self.sig_repr_params['transf'] not in self.implemented_transf:
            raise ValueError(self.sig_repr_params['transf'] +
                             " not implemented - yet?")
        
        if self.verbose:
            print ("Computing the chosen signal representation:",
                   self.sig_repr_params['transf'] )
        
        nc = self.audioObject.channels
        Xchan = []
        for n in range(nc):
            if self.sig_repr_params['transf'] == 'stftold':
                X, freqs, times = ao.stft(
                    self.audioObject.data[:,n],
                    window=np.hanning(self.sig_repr_params['wlen']),
                    hopsize=self.sig_repr_params['hopsize'],
                    nfft=self.sig_repr_params['fsize'],
                    fs=self.audioObject.samplerate
                    )
            else:
                self.tft.computeTransform(self.audioObject.data[:,n],)
                X = self.tft.transfo
            Xchan.append(X)
            
        if self.verbose>1:
            print X.shape
        
        self.nbFreqsSigRepr, self.nbFramesSigRepr = X.shape
        ##assert self.nbFreqsSigRepr == self.tft.freqbins
        del X
        del self.audioObject.data
        
        if nc == 1:
            self.Cx = np.abs(Xchan[0])**2
        else:
            self.Cx = np.zeros([nc * (nc + 1) / 2,
                                self.nbFreqsSigRepr,
                                self.nbFramesSigRepr],
                               dtype=complex)
            for n1 in range(nc):
                for n2 in range(n1, nc):
                    # note : we keep only upper diagonal of Cx
                    # lower diagonal is conjugate of upper one.
                    n = n2 - n1 + np.sum(np.arange(nc, nc-n1, -1))
                    self.Cx[n] = Xchan[n1] * np.conj(Xchan[n2])
        
        if self.noise['ann_PSD_lim'][0] is None or \
               self.noise['ann_PSD_lim'][1] is None:
            mix_psd = 0
            # average power, for each frequency band, across the frames
            if nc == 1:
                mix_psd += np.mean(self.Cx, axis=1)
            else:
                for n1 in range(nc):
                    n = np.sum(np.arange(nc, nc-n1, -1)) # n2 = n1
                    mix_psd += np.mean(self.Cx[n], axis=1)
                    
            if self.verbose>1:
                print "mix_psd", mix_psd
            mix_psd /= nc
            if self.verbose>1:
                print "mix_psd/nc", mix_psd
            if self.noise['ann_PSD_lim'][0] is None:
                self.noise['ann_PSD_lim'][0] = np.real(mix_psd) / 100.
            if self.noise['ann_PSD_lim'][1] is None:
                self.noise['ann_PSD_lim'][1] = np.real(mix_psd) / 10000.
        if self.noise['sim_ann_opt'] in ('ann'):
            self.noise['PSD'] = self.noise['ann_PSD_lim'][0]
        
        # useless for the rest of computations:
        del Xchan
    
    def estim_param_a_post_model(self,):
        """Estimates the _a posteriori_ model for the provided
        audio signal. In particular, this runs self.iter_num times
        the Generalized Expectation-Maximisation algorithm to
        update the various parameters of the model, so as to
        maximize the likelihood of the data given these parameters.
        
        From these parameters, the posterior expectation of the
        \"hidden\" or latent variables (here the spatial and spectral
        components) can be computed, leading to the estimation of the
        separated underlying sources.

        Consider using ``self.separate\_spat\_comps`` or
        ``self.separate\_spatial\_filter\_comp`` to obtain the separated time
        series, once the parameters have been estimated.
        """
        
        logliks = np.ones(self.iter_num)
        
        # TODO: move this back in __init__, and remove from subclasses...
        if self.noise['sim_ann_opt'] in ['ann', ]:
            self.noise['PSD'] = self.noise['ann_PSD_lim'][0]
        elif self.noise['sim_ann_opt'] is 'no_ann':
            self.noise['PSD'] = self.noise['ann_PSD_lim'][1]
        else:
            warnings.warn("To add noise to the signal, provide the "+
                          "sim_ann_opt from any of 'ann', "+
                          "'no_ann' or 'ann_ns_inj' ")
            
        for i in range(self.iter_num):
            if self.verbose:
                print "Iteration", i+1, "on", self.iter_num
            # adding the noise psd if required:
            if self.noise['sim_ann_opt'] in ['ann', 'ann_ns_inj']:
                self.noise['PSD'] = (
                    (np.sqrt(self.noise['ann_PSD_lim'][0]) *
                     (self.iter_num - i) +
                     np.sqrt(self.noise['ann_PSD_lim'][1]) * i) /
                    self.iter_num) ** 2
                
            # running the GEM iteration:
            logliks[i] = self.GEM_iteration()
            if self.verbose:
                print "    log-likelihood:", logliks[i]
                if i>0:
                    print "        improvement:", logliks[i]-logliks[i-1]

        return logliks
    
    def GEM_iteration(self,):
        """GEM iteration
        """
        if self.audioObject.channels==2:
            spat_comp_powers, mix_matrix, rank_part_ind = (
                self.retrieve_subsrc_params())
            
            # compute the sufficient statistics
            hat_Rxx, hat_Rxs, hat_Rss, hat_Ws, loglik = (
                self.compute_suff_stat(spat_comp_powers, mix_matrix))
            
            # update the mixing matrix
            self.update_mix_matrix(hat_Rxs, hat_Rss, mix_matrix, rank_part_ind)
            
            # from sub-sources to sources
            # (as given by the different spatial comps)
            #     had better have shape = [nbSpatComps,F,N]
            hat_W = np.zeros([len(rank_part_ind),
                              self.nbFreqsSigRepr,
                              self.nbFramesSigRepr])
            if self.verbose > 1:
                print "rank_part_in", rank_part_ind
            for w in range(len(rank_part_ind)):
                hat_W[w] = np.mean(hat_Ws[rank_part_ind[w]], axis=0)
                
            del spat_comp_powers, mix_matrix, rank_part_ind
            del hat_Rxx, hat_Rxs, hat_Rss, hat_Ws
        else:
            raise AttributeError("Nb channels "+str(self.audioObject.channels)+
                                 " not implemented yet")
        
        # update the spectral parameters
        self.update_spectral_components(hat_W)
        
        # normalize parameters
        self.renormalize_parameters()
        
        return loglik
    
    def comp_spat_comp_power(self, spat_comp_ind,
                             spec_comp_ind=[], factor_ind=[]):
        """
    Matlab FASST Toolbox help::
        
        % V = comp_spat_comp_power(mix_str, spat_comp_ind,                  
        %                          spec_comp_ind, factor_ind);            
        %
        % compute spatial component power
        %
        %
        % input
        % -----
        %
        % mix_str           : mixture structure
        % spat_comp_ind     : spatial component index
        % spec_comp_ind     : (opt) factor index (def = [], use all components)
        % factor_ind         : (opt) factor index (def = [], use all factors)
        % 
        %
        % output
        % ------
        %
        % V                 : (F x N) spatial component power
        
        """
        V = np.zeros([self.nbFreqsSigRepr, self.nbFramesSigRepr])
        if len(spec_comp_ind):
            spec_comp_ind_arr = spec_comp_ind
        else:
            spec_comp_ind_arr = self.spec_comps.keys()
        
        for k in spec_comp_ind_arr:
            if spat_comp_ind == self.spec_comps[k]['spat_comp_ind']:
                V_comp = np.ones([self.nbFreqsSigRepr, self.nbFramesSigRepr])
                if len(factor_ind):
                    factors_ind_arr = factor_ind
                else:
                    factors_ind_arr = self.spec_comps[k]['factor'].keys()
                    
                for f in factors_ind_arr:
                    factor = self.spec_comps[k]['factor'][f]
                    W = np.dot(factor['FB'], factor['FW'])
                    if len(factor['TB']):
                        H = np.dot(factor['TW'],factor['TB'])
                    else:
                        H = factor['TW']
                    V_comp *= np.dot(W, H)
                    del W
                    del H
                    
                V += V_comp
                del V_comp
                del factor
        
        return V
    
    def comp_spat_cmps_powers(self, spat_comp_ind,
                              spec_comp_ind=[], factor_ind=[]):
        """Compute the sum of the spectral powers corresponding to the
        spatial components as provided in the list `spat_comp_ind`
        
        NB: because this does not take into account the mixing process,
        the resulting power does not, in general, correspond to the
        the observed signal's parameterized spectral power.
        """
        V = 0
        for i in spat_comp_ind:
            V += self.comp_spat_comp_power(spat_comp_ind=i)
        return V
    
    def retrieve_subsrc_params(self,):
        """Computes the various quantities necessary for the estimation of the
        main parameters:
        
        **Outputs**
        spat_comp_powers
            (total_spat_rank x nbFreqsSigRepr x nbFramesSigRepr) ndarray
            the spatial component power spectra. Note that total_spat_rank
            is the sum of all the spatial ranks for all the sources.
        mix_matrix
            (total_spat_rank x nchannels x nbFreqsSigRepr) ndarray
            the mixing matrices for each source
        rank_part_ind
            dictionary: each key is one source, and the values are the indices
            in spat_comp_powers and mix_matrix that correspond to that source.
            If the spatial rank of source j is 2, then its spectra will appear
            twice in spat_comp_powers, with mixing parameters (potentially
            different one from the other) appearing in two sub-matrices of
            mix_matrix.
        """
        K = len(self.spat_comps)
        rank_total = 0
        rank_part_ind = {}
        for j in range(K):
            # this is the ranks
            if self.spat_comps[j]['mix_type'] == 'inst':
                rank = self.spat_comps[j]['params'].shape[1]
            else:
                rank = self.spat_comps[j]['params'].shape[0]
            if self.verbose>1:
                print "    Rank of spatial source %d" %j +\
                      " is %d" %rank
            rank_part_ind[j] = (
                rank_total +
                np.arange(rank))
            rank_total += rank
        
        spat_comp_powers = np.zeros([rank_total,
                                     self.nbFreqsSigRepr,
                                     self.nbFramesSigRepr])
        
        mix_matrix = np.zeros([rank_total,
                               self.audioObject.channels,
                               self.nbFreqsSigRepr], dtype=complex)
        for j, spat_comp in self.spat_comps.items():
            spat_comp_j = self.comp_spat_comp_power(spat_comp_ind=j)
            for r in rank_part_ind[j]:
                spat_comp_powers[r] = spat_comp_j
            if spat_comp['mix_type'] == 'inst':
                for f in range(self.nbFreqsSigRepr):
                    #print rank_part_ind[j]
                    #print spat_comp['params'].shape
                    #print mix_matrix[rank_part_ind[j],:,f].shape
                    mix_matrix[rank_part_ind[j],:,f] = spat_comp['params'].T
            else:
                mix_matrix[rank_part_ind[j]] = spat_comp['params']
                
        return spat_comp_powers, mix_matrix, rank_part_ind
    
    def compute_suff_stat(self, spat_comp_powers, mix_matrix):
        """
        
        Outputs:
        hat_Rxx
        hat_Rxs
        hat_Rss
        hat_Ws
        loglik
        """
        if self.audioObject.channels != 2:
            raise ValueError("Nb channels not supported:"+
                             str(self.audioObject.channels))
        
        if self.verbose: print "    Computing sufficient statistics"
        nbspatcomp = spat_comp_powers.shape[0]
        
        sigma_x_diag = np.zeros([2,
                                 self.nbFreqsSigRepr,
                                 self.nbFramesSigRepr])
        sigma_x_off = np.zeros([self.nbFreqsSigRepr,
                                self.nbFramesSigRepr], dtype=complex)
        for n in range(2):
            sigma_x_diag[n] += np.vstack(self.noise['PSD'])
            # noise PSD should be of size nbFreqs
        
        for r in range(nbspatcomp):
            sigma_x_diag[0] += (
                np.vstack(np.abs(mix_matrix[r][0])**2) *
                spat_comp_powers[r]
                )
            sigma_x_diag[1] += (
                np.vstack(np.abs(mix_matrix[r][1])**2) *
                spat_comp_powers[r]
                )
            sigma_x_off += (
                np.vstack(mix_matrix[r][0] *
                          np.conj(mix_matrix[r][1])) *
                spat_comp_powers[r]
                )
            
        inv_sigma_x_diag, inv_sigma_x_off, det_sigma_x = (
            self.inv_herm_mat_2d(sigma_x_diag, sigma_x_off))
        del sigma_x_diag, sigma_x_off
        
        # compute log likelihood
        loglik = - np.mean(np.log(det_sigma_x * np.pi) +
                           inv_sigma_x_diag[0] * self.Cx[0] +
                           inv_sigma_x_diag[1] * self.Cx[2] +
                           2. * np.real(inv_sigma_x_off * np.conj(self.Cx[1]))
                           )
        # compute expectations of Rss and Ws sufficient statistics
        Gs = {}
        # one for each channel (stereo, here)
        Gs[0] = {}
        Gs[1] = {}
        for r in range(nbspatcomp):
            Gs[0][r] = (
                (np.vstack(np.conj(mix_matrix[r][0])) * inv_sigma_x_diag[0] +
                 np.vstack(np.conj(mix_matrix[r][1])) *
                 np.conj(inv_sigma_x_off)) *
                spat_comp_powers[r]
                )
            
            Gs[1][r] = (
                (np.vstack(np.conj(mix_matrix[r][0])) * inv_sigma_x_off +
                 np.vstack(np.conj(mix_matrix[r][1])) * inv_sigma_x_diag[1]) *
                spat_comp_powers[r]
                )
            
        hat_Rss = np.zeros([self.nbFreqsSigRepr,
                            nbspatcomp,
                            nbspatcomp],
                           dtype=complex)
        hat_Ws = np.zeros([nbspatcomp,
                           self.nbFreqsSigRepr,
                           self.nbFramesSigRepr])
        hatRssLoc1 = np.zeros_like(self.Cx[0])
        hatRssLoc2 = np.zeros_like(self.Cx[0])
        hatRssLoc3 = np.zeros_like(self.Cx[0])
        for r1 in range(nbspatcomp):
            for r2 in range(nbspatcomp):
                # TODO: could probably factor a bit more the following formula:
                ## hatRssLoc1[:] = (Gs[0][r1] * np.conj(Gs[0][r2]) * self.Cx[0] + Gs[1][r1] * np.conj(Gs[1][r2]) * self.Cx[2] +Gs[0][r1] * np.conj(Gs[1][r2]) * self.Cx[1] +Gs[1][r1] * np.conj(Gs[0][r2]) *np.conj(self.Cx[1]) -(Gs[0][r1] * np.vstack(mix_matrix[r2][0]) + Gs[1][r1] * np.vstack(mix_matrix[r2][1])) *spat_comp_powers[r2]  )
                hatRssLoc1[:] = np.copy(self.Cx[0])
                hatRssLoc1 *= np.conj(Gs[0][r2])
                hatRssLoc1 += (np.conj(Gs[1][r2]) * self.Cx[1])
                hatRssLoc1 *= Gs[0][r1]
                
                hatRssLoc2[:] = np.copy(self.Cx[2])
                hatRssLoc2 *= np.conj(Gs[1][r2])
                hatRssLoc2 += (np.conj(Gs[0][r2]) * np.conj(self.Cx[1]))
                hatRssLoc2 *= Gs[1][r1]
                
                hatRssLoc3[:] = np.copy(Gs[0][r1])
                hatRssLoc3 *= np.vstack(mix_matrix[r2][0])
                hatRssLoc3 += (Gs[1][r1] * np.vstack(mix_matrix[r2][1]))
                hatRssLoc3 *= spat_comp_powers[r2]
                
                hatRssLoc1 += hatRssLoc2
                hatRssLoc1 -= hatRssLoc3
                
                #hatRssLoc = (Gs[0][r1] * np.conj(Gs[0][r2]) * self.Cx[0] +
                #             Gs[1][r1] * np.conj(Gs[1][r2]) * self.Cx[2] +
                #             Gs[0][r1] * np.conj(Gs[1][r2]) * self.Cx[1] +
                #             Gs[1][r1] * np.conj(Gs[0][r2]) * np.conj(self.Cx[1]) -
                #             (Gs[0][r1] * np.vstack(mix_matrix[r2][0]) +
                #              Gs[1][r1] * np.vstack(mix_matrix[r2][1]))
                #             * spat_comp_powers[r2]
                #             )
                if r1 == r2:
                    hatRssLoc1 += spat_comp_powers[r1]
                    hat_Ws[r1] = np.abs(np.real(hatRssLoc1))
                    
                hat_Rss[:,r1,r2] = np.mean(hatRssLoc1, axis=1)
                
        # To assure hermitian symmetry:
        for f in range(self.nbFreqsSigRepr):
            hat_Rss[f] = (hat_Rss[f] + np.conj(hat_Rss[f]).T) / 2.
            
        # Expectations of Rxs sufficient statistics
        hat_Rxs = np.zeros([self.nbFreqsSigRepr,
                            2,
                            nbspatcomp],
                           dtype=complex)
        for r in range(nbspatcomp):
            hat_Rxs[:,0,r] = (
                np.mean(np.conj(Gs[0][r]) * self.Cx[0] +
                        np.conj(Gs[1][r]) * self.Cx[1], axis=1)
                )
            hat_Rxs[:,1,r] = (
                np.mean(np.conj(Gs[0][r]) * np.conj(self.Cx[1]) +
                        np.conj(Gs[1][r]) * self.Cx[2], axis=1)
                )
        
        del Gs
        
        # at last Rxx sufficient statistics:
        hat_Rxx = np.mean(self.Cx, axis=-1)
        # recommendation, use logarithm:
        # hat_Rxx[]
        
        return hat_Rxx, hat_Rxs, hat_Rss, hat_Ws, loglik
    
    def inv_herm_mat_2d(self, sigma_x_diag, sigma_x_off):
        """Computes the inverse of 2D hermitian matrices.

        Inputs
        ------
        sigma_x_diag
            ndarray, with (dim of axis=0) = 2
            
            The diagonal elements of the matrices to invert.
            sigma_x_diag[0] are the (0,0) elements and
            sigma_x_diag[1] are the (1,1) ones.
            
        sigma_x_off
            ndarray, with the same dimensions as sigma_x_diag[0]
            
            The off-diagonal elements of the matrices, more precisely the
            (0,1) element (since the matrices are assumed Hermitian,
            the (1,0) element is the complex conjugate)
        
        Outputs
        -------
        inv_sigma_x_diag
            ndarray, 2 x shape(sigma_x_off)

            Diagonal elements of the inverse matrices.
            [0] <-> (0,0)
            [1] <-> (1,1)

        inv_sigma_x_off
            ndarray, shape(sigma_x_off)
            
            Off-diagonal (0,1) elements of the inverse matrices

        det_sigma_x
            ndarray, shape(sigma_x_off)
            
            For each inversion, the determinant of the matrix.
        
        Remarks
        -------
        The inversion is done explicitly, by computing the determinant
        (explicit formula for 2D matrices), then the elements of the
        inverse with the corresponding formulas.
        
        To deal with ill-conditioned matrices, a minimum (absolute) value of
        the determinant is guaranteed. 
        
        """
        #if len(sigma_x_diag.shape) != 3:
        #    raise ValueError("Something weird happened to sigma_x")
        det_sigma_x = np.prod(sigma_x_diag, axis=0) - np.abs(sigma_x_off)**2
        if self.verbose:
            print "number of 0s in det ",(det_sigma_x==0.).sum()
        # issue when det sigma x is 0... 
        det_sigma_x = (
            np.sign(det_sigma_x + eps) *
            np.maximum(np.abs(det_sigma_x), eps))
        if self.verbose:
            print "number of 0s left in det", (det_sigma_x==0.).sum()
        inv_sigma_x_diag = np.zeros_like(sigma_x_diag)
        inv_sigma_x_off = - sigma_x_off / det_sigma_x
        inv_sigma_x_diag[0] = sigma_x_diag[1] / det_sigma_x
        inv_sigma_x_diag[1] = sigma_x_diag[0] / det_sigma_x
        
        return inv_sigma_x_diag, inv_sigma_x_off, det_sigma_x
    
    def update_mix_matrix(self,hat_Rxs, hat_Rss, mix_matrix, rank_part_ind):
        """
        """
        # deriving which components have which updating rule:
        upd_inst_ind = []
        upd_inst_other_ind = []
        upd_conv_ind = []
        upd_conv_other_ind = []
        for j, spat_comp_j in self.spat_comps.items():
            if spat_comp_j['frdm_prior'] == 'free' and \
                   spat_comp_j['mix_type'] == 'inst':
                upd_inst_ind.extend(rank_part_ind[j])
            else:
                upd_inst_other_ind.extend(rank_part_ind[j])
            
            if spat_comp_j['frdm_prior'] == 'free' and \
                   spat_comp_j['mix_type'] == 'conv':
                upd_conv_ind.extend(rank_part_ind[j])
            else:
                upd_conv_other_ind.extend(rank_part_ind[j])
        
        # update linear instantaneous coefficients:
        K_inst = len(upd_inst_ind)
        
        if len(upd_inst_ind):
            if self.verbose:
                print "    Updating mixing matrix, instantaneous sources"
            #hat_Rxs_bis = np.zeros([self.nbFreqsSigRepr,
            #                        2,
            #                        K_inst])
            hat_Rxs_bis = hat_Rxs[:,:,upd_inst_ind]
            if len(upd_inst_other_ind):
                for f in range(self.nbFreqsSigRepr):
                    hat_Rxs_bis[f] -= (
                        np.dot(mix_matrix[upd_inst_other_ind,:,f].T,
                               hat_Rss[f][np.vstack(upd_inst_other_ind),
                                                        upd_inst_ind]))
                    # hat_Rss[f][upd_inst_other_ind][:,upd_inst_ind])
            hat_Rxs_bis = np.real(np.mean(hat_Rxs_bis, axis=0))
            rm_hat_Rss = np.real(np.mean(hat_Rss[:,np.vstack(upd_inst_ind),
                                                 upd_inst_ind], axis=0))
            
            # in ozerov's code:
            ##mix_matrix_inst = np.dot(hat_Rxs_bis, np.linalg.inv(rm_hat_Rss))
            mix_matrix_inst = np.linalg.solve(rm_hat_Rss.T, hat_Rxs_bis.T)
            #                                   sym_pos=True).T
            if self.verbose>1:
                print "mix_matrix", mix_matrix
                print "mix_matrix_inst", mix_matrix_inst
                print "mix_matrix_inst.shape",mix_matrix_inst.shape
                print mix_matrix.shape, \
                      mix_matrix[upd_inst_ind].shape
            for f in range(self.nbFreqsSigRepr):
                mix_matrix[upd_inst_ind,:,f] = mix_matrix_inst
                
            del mix_matrix_inst
            
        # update convolutive coefficients: 
        if len(upd_conv_ind):
            if self.verbose:
                print "    Updating mixing matrix, convolutive sources"
            hat_Rxs_bis = hat_Rxs[:,:,upd_conv_ind]
            if len(upd_conv_other_ind):
                for f in range(self.nbFreqsSigRepr):
                    hat_Rxs_bis[f] -= (
                        np.dot(mix_matrix[upd_conv_other_ind,:,f].T,
                               hat_Rss[f][np.vstack(upd_conv_other_ind),
                                          upd_conv_ind]))
            for f in range(self.nbFreqsSigRepr):
                try:
                    mix_matrix[upd_conv_ind,:,f] = (
                        np.linalg.solve(hat_Rss[f].T, hat_Rxs_bis[f].T))
                except np.linalg.linalg.LinAlgError:
                    print "hat_Rss[f]:", hat_Rss[f]
                    print "hat_Rxs_bis[f]:", hat_Rxs_bis[f]
                    raise np.linalg.LinAlgError('Singular Matrix')
                except:
                    raise # re-raise the exception if that was not linalgerror...
                    
            ## smoothing
            ##for n in upd_conv_ind:
            ##    for nc in range(self.audioObject.channels):
            ##        smoothAbsMix = (
            ##            st.medianFilter(np.abs(mix_matrix[n,nc,:]),
            ##                            length=self.nbFreqsSigRepr/200)
            ##            )
            ##        mix_matrix[n,nc,:] = (
            ##            smoothAbsMix *
            ##            np.exp(1j * np.angle(mix_matrix[n,nc,:]))
            ##            )
            
        # update the matrix in the component parameters:
        for k, spat_comp_k in self.spat_comps.items():
            if spat_comp_k['frdm_prior'] == 'free':
                if spat_comp_k['mix_type'] == 'inst':
                    spat_comp_k['params'] = (
                        np.mean(mix_matrix[rank_part_ind[k]], axis=2)).T
                else:
                    spat_comp_k['params'] = (
                        mix_matrix[rank_part_ind[k]])
                    
        # mix_matrix should have changed outside this method... TBC
        # should we normalize here?
        ##self.renormalize_parameters()
        
    def separate_spatial_filter_comp(self,
                                     dir_results=None,
                                     suffix=None):
        """separate_spatial_filter_comp
        
        Separates the sources using only the estimated spatial
        filter (i.e. the mixing parameters in self.spat_comps[j]['params'])
        
        In particular, we consider here the corresponding MVDR filter,
        as exposed in::
        
         Maazaoui, M.; Grenier, Y. & Abed-Meraim, K.
         ``Blind Source Separation for Robot Audition using
         Fixed Beamforming with HRTFs'', 
         in proc. of INTERSPEECH, 2011.
        
        per channel, the filter steering vector, source p:
        
        .. math::
        
            b(f,p) = \\frac{R_{aa,f}^{-1} a(f,p)}{a^{H}(f,p) R_{aa,f}^{-1} a(f,p)}
            
        with
        
        .. math::
        
            R_{aa,f} = \\sum_q a(f,q) a^{H}(f,q)
            
        It corresponds also to the given model in FASST, assuming that all the
        spectral powers are equal across all sources. Here, by computing the Wiener
        Gain WG to get the images, we actually have
        
        .. math::
        
            b(f,p) a(f,p)^H
            
        and the denominator therefore is the trace of the \"numerator\".
        
        """
        # grouping the indices by spatial component
        spec_comp_ind = {}
        for spat_ind in range(len(self.spat_comps)):
            spec_comp_ind[spat_ind] = []
        for spec_ind, spec_comp in self.spec_comps.items():
            # add the spec comp index to the corresponding spatial comp:
            spec_comp_ind[spec_comp['spat_comp_ind']].append(spec_ind)
            
        # copying from separate_spec_comps -  could modify that one later...
        if dir_results is None:
            dir_results = (
                '/'.join(
                self.audioObject.filename.split('/')[:-1])
                )
            if self.verbose:
                print "Writing to same directory as input file: " + dir_results
        
        nc = self.audioObject.channels
        if nc != 2:
            raise NotImplementedError()
        
        nbSources = len(spec_comp_ind)
        sigma_comps_diag = np.zeros([nbSources, 2,
                                    self.nbFreqsSigRepr,
                                    self.nbFramesSigRepr])
        sigma_comps_off = np.zeros([nbSources,
                                   self.nbFreqsSigRepr,
                                   self.nbFramesSigRepr], dtype=np.complex)
        
        # computing individual spatial variance
        R_diag0 = np.zeros([nbSources, self.nbFreqsSigRepr])
        R_diag1 = np.zeros([nbSources, self.nbFreqsSigRepr])
        R_off  = np.zeros([nbSources, self.nbFreqsSigRepr], dtype=np.complex)
        
        for n in range(nbSources):
            if self.spat_comps[n]['mix_type'] == 'inst':
                raise NotImplementedError('Mixing params not convolutive...')
                mix_coefficients = self.spat_comps[n]['params'].T
                # mix_coefficients.shape should be (rank, nchannels)
            elif self.spat_comps[n]['mix_type'] == 'conv':
                mix_coefficients = self.spat_comps[n]['params']
                # mix_coefficients.shape should be (rank, nchannels, freq)
            
            # R_diag = np.zeros(2, self.nbFreqsSigRepr)
            R_diag0[n] = np.atleast_1d(
                (np.abs(mix_coefficients[:, 0])**2).sum(axis=0))
            R_diag1[n] = np.atleast_1d(
                        (np.abs(mix_coefficients[:, 1])**2).sum(axis=0))
            # element at (1,2): 
            R_off[n] = np.atleast_1d((
                mix_coefficients[:, 0] *
                np.conj(mix_coefficients[:, 1])).sum(axis=0))
            
        Raa_00 = np.mean(R_diag0, axis=0)
        Raa_11 = np.mean(R_diag1, axis=0)
        Raa_01 = np.mean(R_off, axis=0)
        inv_Raa_diag, inv_Raa_off, det_mat = inv_mat([Raa_00, Raa_11],
                                                     Raa_01)
        
        if not hasattr(self, 'files'):
            self.files = {}
            
        self.files['spatial'] = []
        
        fileroot = self.audioObject.filename.split('/')[-1][:-4]
        for n in range(nbSources):
            WG = self.compute_Wiener_gain_2d(
                    [R_diag0[n], R_diag1[n]],
                    R_off[n],
                    inv_Raa_diag,
                    inv_Raa_off,
                timeInvariant=True)
            normalization = np.real(WG[0,0] + WG[1,1])
            WG /= [[normalization]]
            if self.sig_repr_params['transf'] is 'stftold':
                # compute the stft/istft
                ndata = ao.filter_stft(
                    self.audioObject.data, WG, analysisWindow=None,
                    synthWindow=np.hanning(self.sig_repr_params['wlen']),
                    hopsize=self.sig_repr_params['hopsize'],
                    nfft=self.sig_repr_params['fsize'],
                    fs=self.audioObject.samplerate)
            else:
                #raise NotImplementedError("TODO")
                X = []
                for chan1 in range(nc):
                    self.tft.computeTransform(
                        self.audioObject.data[:,chan1])
                    X.append(self.tft.transfo)
                ndata = []
                if WG.ndim == 3:
                    for chan1 in range(nc):
                        self.tft.transfo = np.zeros([self.nbFreqsSigRepr,
                                                     self.nbFramesSigRepr],
                                                    dtype=np.complex)
                        for chan2 in range(nc):
                            self.tft.transfo += (
                                np.vstack(WG[chan1, chan2])
                                * X[chan2])
                        ndata.append(self.tft.invertTransform())
                        del self.tft.transfo
                elif WG.ndim == 4:
                    for chan1 in range(nc):
                        self.tft.transfo = np.zeros([self.nbFreqsSigRepr,
                                                     self.nbFramesSigRepr],
                                                    dtype=np.complex)
                        for chan2 in range(nc):
                            self.tft.transfo += (
                                WG[chan1, chan2]
                                * X[chan2])
                        ndata.append(self.tft.invertTransform())
                        del self.tft.transfo
                        
                ndata = np.array(ndata).T
                
            _suffix = '_spatial'
            if suffix is not None and n in suffix:
                _suffix += '_' + suffix[n]
            outAudioName = (
                dir_results + '/' + fileroot + '_' + str(n) + 
                '-' + str(nbSources) + _suffix + '.wav')
            self.files['spatial'].append(outAudioName)
            outAudioObj = ao.AudioObject(filename=outAudioName,
                                         mode='w')
            outAudioObj._data = np.int16(
                ndata[:self.audioObject.nframes,:] *
                self.audioObject._maxdata)#(2**15))
            outAudioObj._maxdata = 1
            outAudioObj._encoding = 'pcm16'
            outAudioObj.samplerate = self.audioObject.samplerate
            outAudioObj._write()
        
    def separate_spat_comps(self,
                            dir_results=None,
                            suffix=None):
        """separate_spat_comps
        
        This separates the sources for each spatial component.
        
        """
        spec_comp_ind = {}
        for spat_ind in range(len(self.spat_comps)):
            spec_comp_ind[spat_ind] = []
        for spec_ind, spec_comp in self.spec_comps.items():
            spec_comp_ind[spec_comp['spat_comp_ind']].append(spec_ind)
            
        self.separate_comps(dir_results=dir_results,
                            spec_comp_ind=spec_comp_ind,
                            suffix=suffix)
    
    def separate_comps(self,
                       dir_results=None,
                       spec_comp_ind=None,
                       suffix=None):
        """separate_comps
        
        Separate the sources as defined by the spectral
        components provided in spec_comp_ind.
        
        This function differs from separate_spat_comps in the way
        that it does not assume the sources are defined by their spatial
        positions.
        
        Note: Trying to bring into one method
        ozerov's separate_spec_comps and separate_spat_comps
        """
        if dir_results is None:
            dir_results = (
                '/'.join(
                self.audioObject.filename.split('/')[:-1])
                )
            if self.verbose:
                print "Writing to same directory as input file: " + dir_results
        
        nc = self.audioObject.channels
        if nc != 2:
            raise NotImplementedError()
        
        if spec_comp_ind is None:
            spec_comp_ind = {}
            for spec_ind in range(len(self.spec_comps)):
                spec_comp_ind[spec_ind] = [spec_ind,]
        
        nbSources = len(spec_comp_ind)
        sigma_comps_diag = np.zeros([nbSources, 2,
                                     self.nbFreqsSigRepr,
                                     self.nbFramesSigRepr])
        sigma_comps_off = np.zeros([nbSources,
                                    self.nbFreqsSigRepr,
                                    self.nbFramesSigRepr], dtype=np.complex)
        
        # computing individual source variance
        for n in range(nbSources):
            if self.verbose>1: print "    source",n+1,"out of",nbSources
            spat_comp_ind = np.unique(
                [self.spec_comps[spec_ind]['spat_comp_ind']
                 for spec_ind in spec_comp_ind[n]]
                )
            if self.verbose>1: print "        spat_comp_ind", spat_comp_ind
            for spat_ind in spat_comp_ind:
                if self.verbose>1:
                    print "        spatial comp",spat_ind+1, \
                          "out of", (spat_comp_ind)
                sigma_c_diag, sigma_c_off = (
                    self.compute_sigma_comp_2d(spat_ind, spec_comp_ind[n])
                    )
                sigma_comps_diag[n] += sigma_c_diag
                sigma_comps_off[n] += sigma_c_off
                del sigma_c_diag, sigma_c_off
        # deriving inverse of mix covariance:
        inv_sigma_x_diag, inv_sigma_x_off = self.compute_inv_sigma_mix_2d(
            sigma_comps_diag,
            sigma_comps_off)
        
        if not hasattr(self, "files"):
            self.files = {}
        self.files['spat_comp'] = []
        
        if True: # self # IF TRANSFO is STFT !!!... 20130507 corrected now?
            fileroot = self.audioObject.filename.split('/')[-1][:-4]
            for n in range(nbSources):
                # get the Wiener filters:
                WG = self.compute_Wiener_gain_2d(
                    sigma_comps_diag[n],
                    sigma_comps_off[n],
                    inv_sigma_x_diag,
                    inv_sigma_x_off)
                # compute the stft/istft
                if self.sig_repr_params['transf'] == 'stftold':
                    ndata = ao.filter_stft(
                        self.audioObject.data, WG, analysisWindow=None,
                        synthWindow=np.hanning(self.sig_repr_params['wlen']),
                        hopsize=self.sig_repr_params['hopsize'],
                        nfft=self.sig_repr_params['fsize'],
                        fs=self.audioObject.samplerate)
                else:
                    X = []
                    for chan1 in range(nc):
                        self.tft.computeTransform(
                            self.audioObject.data[:,chan1])
                        X.append(self.tft.transfo)
                    ndata = []
                    if WG.ndim == 3:
                        for chan1 in range(nc):
                            self.tft.transfo = np.zeros([self.nbFreqsSigRepr,
                                                         self.nbFramesSigRepr],
                                                        dtype=np.complex)
                            for chan2 in range(nc):
                                self.tft.transfo += (
                                    np.vstack(WG[chan1, chan2])
                                    * X[chan2])
                            ndata.append(self.tft.invertTransform())
                            del self.tft.transfo
                    elif WG.ndim == 4:
                        for chan1 in range(nc):
                            self.tft.transfo = np.zeros([self.nbFreqsSigRepr,
                                                         self.nbFramesSigRepr],
                                                        dtype=np.complex)
                            for chan2 in range(nc):
                                self.tft.transfo += (
                                    WG[chan1, chan2]
                                    * X[chan2])
                            ndata.append(self.tft.invertTransform())
                            del self.tft.transfo
                        
                    ndata = np.array(ndata).T
                _suffix = ''
                if suffix is not None and n in suffix:
                    _suffix = '_' + suffix[n]
                outAudioName = \
                    dir_results + '/' + fileroot + '_' + str(n) + \
                    '-' + str(nbSources) + _suffix + '.wav'
                self.files['spat_comp'].append(outAudioName)
                outAudioObj = ao.AudioObject(filename=outAudioName,
                                             mode='w')
                outAudioObj._data = np.int16(
                    ndata[:self.audioObject.nframes,:] *
                    self.audioObject._maxdata)#(2**15))
                outAudioObj._maxdata = 1
                outAudioObj._encoding = 'pcm16'
                outAudioObj.samplerate = self.audioObject.samplerate
                outAudioObj._write()
        ## TODO: else for the other transforms
        ##       should work all the same, but with cqt, not very good
        ## means to cut signals and paste them back together...
        
    def mvdr_2d(self,
                theta,
                distanceInterMic=.3,
                ):
        """mvdr_2d(self,
        theta, # in radians
        distanceInterMic=.3, # in meters
        )
        
        MVDR minimum variance distortion-less response spatial
        filter, for a given angle theta and given distance between the mics.
        
        self.Cx is supposed to provide the necessary covariance matrix, for
        the \"Capon\" filter.
        """
        Cx = np.copy(self.Cx)
        Cx[0][:,:] = np.vstack(Cx[0].mean(axis=1))
        Cx[1][:,:] = np.vstack(Cx[1].mean(axis=1))
        Cx[2][:,:] = np.vstack(Cx[2].mean(axis=1))
        if self.verbose>1:
            print Cx
        
        #inv_Cx_diag, inv_Cx_off, det_Cx = self.inv_herm_mat_2d([self.Cx[0],
        #                                                        self.Cx[2]],
        #                                                       self.Cx[1])
        inv_Cx_diag, inv_Cx_off, det_Cx = self.inv_herm_mat_2d([Cx[0],
                                                                Cx[2]],
                                                               Cx[1])
        freqs = (
            np.arange(self.nbFreqsSigRepr) * 1. /
            self.sig_repr_params['fsize'] * self.audioObject.samplerate
            )
        
        filt = gen_steer_vec_far_src_uniform_linear_array(
                   freqs,
                   nchannels=self.audioObject.channels,
                   theta=theta,
                   distanceInterMic=distanceInterMic)
        
        W = np.zeros([self.audioObject.channels, # nc x nc x F x N
                      self.audioObject.channels,
                      self.nbFreqsSigRepr,
                      self.nbFramesSigRepr], dtype=np.complex)
        
        den = (
            np.vstack(np.abs(filt[0])**2) * inv_Cx_diag[0] + 
            np.vstack(np.abs(filt[1])**2) * inv_Cx_diag[1] +
            2 * np.real(
                np.vstack(np.conj(filt[0]) * filt[1]) * inv_Cx_off)
            )
        W[1,1] = (
            np.vstack(filt[1] * np.conj(filt[0])) * inv_Cx_off
            )
        W[0,0] = (
            np.conj(W[1,1]) +
            np.vstack(np.abs(filt[0])**2) * inv_Cx_diag[0] 
            )
        W[1,1] += (
            np.vstack(np.abs(filt[1])**2) * inv_Cx_diag[1] 
            )
        W[0,1] = (
            np.vstack(np.abs(filt[0])**2) * inv_Cx_off +
            np.vstack(filt[0] * np.conj(filt[1])) * np.conj(inv_Cx_diag[1]) 
            )
        W[1,0] = (
            np.vstack(np.abs(filt[1])**2) * np.conj(inv_Cx_off) +
            np.vstack(filt[1] * np.conj(filt[0])) * np.conj(inv_Cx_diag[0])
            )
        #if self.verbose>1:
        #    print W
        # should check that self.sig_repr_params['transf'] == 'stft'
        return ao.filter_stft(
            self.audioObject.data,
            W,
            analysisWindow=np.hanning(self.sig_repr_params['wlen']),
            synthWindow=np.hanning(self.sig_repr_params['wlen']),
            hopsize=self.sig_repr_params['hopsize'],
            nfft=self.sig_repr_params['fsize'],
            fs=self.audioObject.samplerate)
    
    def gcc_phat_tdoa_2d(self):
        """Using the cross-spectrum in self.Cx[1] to estimate the time
        difference of arrival detection function (the Generalized Cross-
        Correllation GCC), with the phase transform (GCC-PHAT) weighing
        function for the cross-spectrum.
        """
        return np.fft.irfft(self.Cx[1]/np.abs(self.Cx[1]),
                            n=self.sig_repr_params['fsize'],
                            axis=0)
    
##    # separate individual components:
##    def separate_spec_comp(self, sep_comp_ind, *args, **kwargs):
##        """
##        """
##        return self.separate_comp(sep_comp_ind)
    
##    def separate_spat_comp(self, spat_comp_ind, *args, **kwargs):
##        """
##        ARGUMENTS
##        ---------
##        spat_comp_ind a list of the spatial components to separate
##            the returned 
##        """
##        spec_comp_ind = []
        
##        for spec_ind, spec_comp in self.spec_comps:
##            if spec_comp['spat_comp_ind'] in spat_comp_ind:
##                spec_comp_ind.append(spec_ind)
        
##        return self.separate_comp(spec_comp_ind, *args, **kwargs)
    
##    def separate_comp(self, spec_comp_ind, filename):
##        """computes the wiener gain for the source represented by
##        the spectral components listed in spec_comp_ind, then
##        computes the time series and writes the output to filename.
##        """
##        if len(spec_comp_ind):
##            pass
    
    def compute_sigma_comp_2d(self, spat_ind, spec_comp_ind):
        """only for stereo case self.audioObject.channels==2
        """
        
        spat_comp_power = self.comp_spat_comp_power(
            spat_comp_ind=spat_ind,
            spec_comp_ind=spec_comp_ind)
        
        # getting the mixing coefficients for corresponding
        # spatial source, depending on mix_type
        if self.spat_comps[spat_ind]['mix_type'] == 'inst':
            mix_coefficients = self.spat_comps[spat_ind]['params'].T
            # mix_coefficients.shape should be (rank, nchannels)
        elif self.spat_comps[spat_ind]['mix_type'] == 'conv':
            mix_coefficients = self.spat_comps[spat_ind]['params']
            # mix_coefficients.shape should be (rank, nchannels, freq)
        
        # R_diag = np.zeros(2, self.nbFreqsSigRepr)
        R_diag0 = np.atleast_1d(
            (np.abs(mix_coefficients[:, 0])**2).sum(axis=0))
        R_diag1 = np.atleast_1d(
            (np.abs(mix_coefficients[:, 1])**2).sum(axis=0))
        # element at (1,2): 
        R_off = np.atleast_1d((
            mix_coefficients[:, 0] *
            np.conj(mix_coefficients[:, 1])).sum(axis=0))
        
        sigma_comp_diag = np.zeros([2,
                                    self.nbFreqsSigRepr,
                                    self.nbFramesSigRepr])
        if self.verbose>1:
            print R_diag0, "R_diag0.shape", R_diag0.shape
            print R_diag1, "R_diag1.shape", R_diag1.shape
            print R_off, "R_off.shape", R_off.shape
        
        sigma_comp_diag[0] = (
            np.vstack(R_diag0) *
            spat_comp_power)
        sigma_comp_diag[1] = (
            np.vstack(R_diag1) *
            spat_comp_power)
        
        sigma_comp_off = (
            np.vstack(R_off) * spat_comp_power)
        
        return sigma_comp_diag, sigma_comp_off
    
    def compute_inv_sigma_mix_2d(self,
                                 sigma_comps_diag,
                                 sigma_comps_off):
        """only for nb channels = 2
        
        sigma_comps_diag ncomp x nchan x nfreq x nframes
        
        """
        sigma_x_diag = sigma_comps_diag.sum(axis=0)
        sigma_x_off = sigma_comps_off.sum(axis=0)
        for n in range(2):
            sigma_x_diag[n] += np.vstack(self.noise['PSD'])
            # noise PSD should be of size nbFreqs
        
        inv_sigma_x_diag, inv_sigma_x_off, _ = (
            self.inv_herm_mat_2d(sigma_x_diag, sigma_x_off))
        
        del sigma_x_diag, sigma_x_off
        
        return inv_sigma_x_diag, inv_sigma_x_off
    
    def compute_Wiener_gain_2d(self,
                               sigma_comp_diag,
                               sigma_comp_off,
                               inv_sigma_mix_diag,
                               inv_sigma_mix_off,
                               timeInvariant=False):
        """
        Matlab FASST Toolbox help::
        
            % WG = comp_WG_spat_comps(mix_str);
            %
            % compute Wiener gains for spatial components
            %
            %
            % input
            % -----
            %
            % mix_str           : input mix structure
            % 
            %
            % output
            % ------
            %
            % WG                : Wiener gains [M x M x F x N x K_spat]
            %
            %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
            % Flexible Audio Source Separation Toolbox (FASST), Version 1.0
            %
            % Copyright 2011 Alexey Ozerov, Emmanuel Vincent and Frederic Bimbot
            % (alexey.ozerov -at- inria.fr, emmanuel.vincent -at- inria.fr,
            %  frederic.bimbot -at- irisa.fr)     
            %
            % This software is distributed under the terms of the GNU Public 
            % License version 3 (http://www.gnu.org/licenses/gpl.txt)
            %
            % If you use this code please cite this research report
            %
            % A. Ozerov, E. Vincent and F. Bimbot
            % \"A General Flexible Framework for the Handling of Prior
            % Information in Audio Source Separation,\" 
            % IEEE Transactions on Audio, Speech and Signal Processing 20(4),
            % pp. 1118-1133 (2012).
            % Available: http://hal.inria.fr/hal-00626962/
            %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
        
        """
        # Here, WG is given by the product:
        #     np.dot(sigma_comp
        if timeInvariant:
            WG = np.zeros([2, 2,
                           self.nbFreqsSigRepr,],
                          dtype=complex)# stands for Wiener Gains
        else:
            WG = np.zeros([2, 2,
                           self.nbFreqsSigRepr,
                           self.nbFramesSigRepr],
                          dtype=complex)# stands for Wiener Gains
        WG[0,0] = sigma_comp_off * np.conj(inv_sigma_mix_off)
        WG[1,1] = np.conj(WG[0,0])
        WG[0,0] += sigma_comp_diag[0] * inv_sigma_mix_diag[0]
        WG[1,1] += sigma_comp_diag[1] * inv_sigma_mix_diag[1]
        
        WG[0,1] = (
            sigma_comp_diag[0] * inv_sigma_mix_off +
            sigma_comp_off * inv_sigma_mix_diag[1]
            )
        WG[1,0] = (
            np.conj(sigma_comp_off) * inv_sigma_mix_diag[0] +
            sigma_comp_diag[1] * np.conj(inv_sigma_mix_off)
            )
        
        return WG
    
    def update_spectral_components(self, hat_W):
        """Update the spectral components,
        with hat_W as the expected value of power
        """
        if self.verbose:
            print "    Update the spectral components"
        omega = self.nmfUpdateCoeff
        nbspeccomp = len(self.spec_comps)
        
        for spec_comp_ind, spec_comp in self.spec_comps.items():
            nbfactors = len(spec_comp['factor'])
            spat_comp_ind = spec_comp['spat_comp_ind']
            
            # DEBUG
            if self.lambdaCorr > 0: # min inter-src correlation approach
                # this is the sum of all the spatial component powers
                spat_comp_powers = np.maximum(self.comp_spat_cmps_powers(
                    self.spat_comps.keys()), eps)
                ### we need the squared of that matrix too:
                ##spat_comp_powers_sqd = spat_comp_powers ** 2
                # the initial spatial comp. power of the current comp:
                spat_comp_power = (
                    np.maximum(
                        self.comp_spat_comp_power(
                            spat_comp_ind,
                            #spec_comp_ind=[spec_comp_ind],
                            ),
                        eps)
                    )
                # ... and removing from the other powers - for correlation
                # control:
                spat_comp_pow_minus = spat_comp_powers - spat_comp_power
                
                if np.all(spat_comp_pow_minus >=0): # DEBUG
                    warnings.warn(
                        "Not all spat_comp_pow_minus, "+
                        "%d negative values!" %np.sum(spat_comp_pow_minus >=0))
                    spat_comp_pow_minus = np.maximum(spat_comp_pow_minus, eps)
                
            for fact_ind, factor in spec_comp['factor'].items():
                # update FB - freq basis
                other_fact_ind_arr = range(nbfactors)
                other_fact_ind_arr.remove(fact_ind)
                other_fact_power = (
                    np.maximum(
                        self.comp_spat_comp_power(
                            spat_comp_ind=spat_comp_ind,
                            spec_comp_ind=[spec_comp_ind],
                            factor_ind=other_fact_ind_arr),
                        eps)
                    )
                if factor['FB_frdm_prior'] == 'free':
                    if self.verbose>1:
                        print "    Updating frequency basis %d-%d" %(
                            spec_comp_ind, fact_ind)
                    spat_comp_power = (
                        np.maximum(
                            self.comp_spat_comp_power(
                                spat_comp_ind,
                                #spec_comp_ind=[spec_comp_ind]
                                ),
                            eps)
                        )
                    #comp_num = hat_W[spat_comp_ind] / spat_comp_power**(2)
                    #comp_den = 1 / spat_comp_power
                    
                    if len(factor['TB']):
                        H = np.dot(factor['TW'], factor['TB'])
                    else:
                        H = factor['TW']
                        
                    FW_H = np.dot(factor['FW'], H).T
                    
                    # denominator + correlation penalization
                    if self.lambdaCorr > 0:
                        corrPen = (
                            self.lambdaCorr
                            * spat_comp_pow_minus #np.maximum(spat_comp_powers,
                            #           eps)
                            / np.maximum(spat_comp_powers**2, eps)
                            )
                    else:
                        corrPen = 0.
                    
                    comp_den = (
                        np.dot(other_fact_power * 
                               (1. / spat_comp_power +
                                corrPen),
                               FW_H))
                    # numerator
                    if self.lambdaCorr > 0:
                        corrPen *= 2 *(
                            spat_comp_power
                            / spat_comp_powers
                            )
                    comp_num = (
                        np.dot((hat_W[spat_comp_ind]
                                / (spat_comp_power**2)
                                # np.maximum(spat_comp_power**(2), eps)
                                + corrPen)
                               * other_fact_power,
                               FW_H))
                    
                    factor['FB'] *= (
                        comp_num / np.maximum(comp_den, eps)) ** omega
                    del comp_num, comp_den, spat_comp_power, H, FW_H
                    
                # update FW - freq weight
                if factor['FW_frdm_prior'] == 'free':
                    if self.verbose>1:
                        print "    Updating frequency weights %d-%d" %(
                            spec_comp_ind, fact_ind)
                    spat_comp_power = (
                        np.maximum(
                            self.comp_spat_comp_power(
                                spat_comp_ind,
                                spec_comp_ind=[spec_comp_ind]),
                            eps)
                        )
                    
                    if len(factor['TB']):
                        H = np.dot(factor['TW'], factor['TB'])
                    else:
                        H = factor['TW']
                        
                    # denominator + correlation penalization
                    if self.lambdaCorr > 0:
                        corrPen = (
                            self.lambdaCorr
                            * np.maximum(spat_comp_pow_minus,#-spat_comp_power,
                                         eps)
                            / np.maximum(spat_comp_powers**2, eps)
                            )
                    else:
                        corrPen = 0.
                    comp_den = (
                        np.dot(factor['FB'].T,
                               np.dot(other_fact_power * 
                                      (1. / spat_comp_power +
                                       corrPen),
                                      #other_fact_power /
                                      #spat_comp_power,
                                      H.T))
                        )
                    
                    # numerator
                    if self.lambdaCorr > 0:# 
                        corrPen *= 2 *(
                            spat_comp_power
                            / spat_comp_powers
                            )
                    comp_num = (
                        np.dot(factor['FB'].T,
                               np.dot((hat_W[spat_comp_ind]
                                       / (spat_comp_power**2) #np.maximum(spat_comp_power**2,eps)
                                       + corrPen)
                                      * other_fact_power,
                                      H.T))
                        )
                    factor['FW'] *= (
                        comp_num / np.maximum(comp_den, eps)) ** omega
                    del comp_num, comp_den, spat_comp_power, H
                    
                # update TW - time weights
                if factor['TW_frdm_prior'] == 'free':
                    if factor['TW_constr'] == 'NMF':
                        if self.verbose>1:
                            print "    Updating time weights %d-%d" %(
                                spec_comp_ind, fact_ind)
                        spat_comp_power = (
                            np.maximum(
                                self.comp_spat_comp_power(
                                    spat_comp_ind,
                                    spec_comp_ind=[spec_comp_ind]),
                                eps)
                            )
                        
                        W = np.dot(factor['FB'], factor['FW'])
                        
                        # correlation penalization
                        if self.lambdaCorr > 0:
                            corrPen = (
                                self.lambdaCorr
                                * np.maximum(spat_comp_pow_minus,
                                             # - spat_comp_power,
                                             eps)
                                / np.maximum(spat_comp_powers**2, eps)
                                )
                            ##if self.verbose>2: # DEBUG
                            ##    # pedantic :
                            ##    print "correlation stuff",
                            ##    print corrPen.mean(), (1./spat_comp_power).mean()
                        else:
                            corrPen = 0.
                        
                        if len(factor['TB']):
                            # denominator
                            comp_den = (
                                np.dot(W.T,
                                       np.dot(other_fact_power * 
                                              (1. / spat_comp_power +
                                               corrPen),#other_fact_power / 
                                              #spat_comp_power,
                                              factor['TB'].T)
                                       )
                                )
                            # numerator
                            if self.lambdaCorr > 0:# corrPen > 0:
                                corrPen *= 2 *(
                                    spat_comp_power
                                    / spat_comp_powers
                                    )
                            comp_num = (
                                np.dot(W.T,
                                       np.dot((hat_W[spat_comp_ind] /
                                               (spat_comp_power**2) #np.maximum(spat_comp_power**2,
                                               #            eps)
                                               + corrPen)
                                              * other_fact_power,
                                              factor['TB'].T)
                                       )
                                )
                        else:
                            # denominator
                            comp_den = (
                                np.dot(W.T,
                                       other_fact_power * 
                                       (1. / spat_comp_power +
                                        corrPen), #other_fact_power / 
                                       #spat_comp_power
                                       )
                                )
                            # numerator
                            if self.lambdaCorr > 0:# corrPen > 0:
                                corrPen *= 2 *(
                                    spat_comp_power
                                    / spat_comp_powers
                                    )
                            ##if self.verbose>5: # DEBUG to discover origin of NaN
                            ##    print "corrPen", corrPen
                            ##    print "other_fact_power", other_fact_power
                            ##    print "hat_W", hat_W[spat_comp_ind]
                            ##    print "squared", np.maximum(spat_comp_power**2,eps)
                                
                            comp_num = (
                                np.dot(W.T,
                                       other_fact_power * (hat_W[spat_comp_ind] /
                                        (spat_comp_power**2)
                                        + corrPen)
                                       )
                                )
                            
                        ##if self.verbose > 8: #DEBUG
                        ##    print "comp_num", comp_num
                        ##    print "comp_den", comp_den
                        factor['TW'] *= (
                            comp_num / np.maximum(comp_den, eps)) ** omega
                        del comp_num, comp_den, spat_comp_power, W
                    elif factor['TW_constr'] in ('GMM', 'GSMM', 'HMM', 'SHMM'):
                        warnings.warn(
                            "The GMM/GSMM/HMM still needs to be adapted "+
                            "to take into account the different factors. ")
                        nbfaccomps = factor['TW'].shape[0]
                        if self.verbose>1:
                            print "    Updating time weights, "+\
                                  "discrete state-based constraints"
                        if len(factor['TB']):
                            errorMsg = "In this implementation, "+\
                                       "as in Ozerov's, non-trivial "+\
                                       "time blobs TB is incompatible with "+\
                                       "discrete state-based constraints for"+\
                                       " the time weights TW"
                            raise AttributeError(errorMsg)
                        
                        if not('TW_all' in factor):
                            factor['TW_all'] = (
                                np.outer(np.ones(nbfaccomps),
                                         np.max(factor['TW'], axis=0))
                                )
                            
                        if 'TW_DP_params' not in factor:
                            if factor['TW_constr'] in ('GMM', 'GSMM'):
                                # prior probabilities
                                factor['TW_DP_params'] = (
                                    np.ones(nbfaccomps) /
                                    np.double(nbfaccomps))
                            else:
                                # transition probabilities
                                factor['TW_DP_params'] = (
                                    np.ones([nbfaccomps, nbfaccomps]) /
                                    np.double(nbfaccomps))
                                
                        if factor['TW_constr'] in ('GMM', 'HMM') and \
                               (np.max(factor['TW_all'])>1 or \
                                np.min(factor['TW_all'])<1):
                            factor['FB'] *= np.mean(factor['TW_all'])
                            factor['TW_all'][:] = 1.
                            
                        if self.verbose:
                            print "    Computing the Itakura Saito distance"+\
                                  " matrix"
                        ISdivMatrix = np.zeros([nbfaccomps,
                                                self.nbFramesSigRepr])
                        for compnb in range(nbfaccomps):
                            factor['TW'][:] = 0
                            factor['TW'][compnb] = factor['TW_all'][compnb]
                            
                            if factor['TW_constr'] not in ('GMM', 'HMM'):
                                # re-estimating the weights for discrete
                                # state model with the constraint on the
                                # single state presence active.
                                # NB: for GMM and HMM, these weights are
                                #     assumed to be 1
                                spat_comp_power = (
                                    np.maximum(
                                        self.comp_spat_comp_power(
                                            spat_comp_ind,
                                            spec_comp_ind=[spec_comp_ind],),
                                        eps)
                                    )
                                 
                                # NMF like updating for estimating the weight
                                Wbasis = np.dot(factor['FB'],
                                                factor['FW'][:,compnb])
                                comp_num = (
                                    np.dot(Wbasis,
                                           hat_W[spat_comp_ind] /
                                           np.maximum(spat_comp_power**2, eps))
                                    )
                                comp_den = (
                                    np.dot(Wbasis,
                                           1 / spat_comp_power)
                                    )
                                
                                factor['TW'][compnb] *= (
                                    comp_num /
                                    np.maximum(comp_den, eps)
                                    ) ** omega
                                
                                factor['TW_all'][compnb]=factor['TW'][compnb]
                                
                                del comp_num, comp_den, spat_comp_power
                                
                            # ratio to compute IS divergence between expected
                            # variance hat_W and the spatial component
                            # with the discrete state restriction
                            spat_comp_power = (
                                np.maximum(
                                self.comp_spat_comp_power(spat_comp_ind),
                                eps)
                                )
                            
                            W_V_ratio = (
                                hat_W[spat_comp_ind] /
                                spat_comp_power)
                            
                            ISdivMatrix[compnb] = (
                                np.sum(W_V_ratio
                                       - np.log(np.maximum(W_V_ratio, eps))
                                       - 1,axis=0)
                                )
                            
                            del W_V_ratio, spat_comp_power
                        
                        # decode the state sequence that minimizes the
                        # track in the IS div matrix, with best
                        # trade-off with the provided TW_DP_params
                        # (temporal constraints)
                        if self.verbose:
                            print "    Decoding the state sequence"
                        if factor['TW_constr'] in ('GMM', 'GSMM'):
                            active_state_seq = (
                                np.argmin(
                                    ISdivMatrix -
                                    np.vstack(
                                        np.log(factor['TW_DP_params'] + eps)),
                                    axis=0)
                                )
                            del ISdivMatrix
                        elif factor['TW_constr'] in ('HMM', 'SHMM'):
                            if self.verbose:
                                print "        Viterbi algorithm to "+\
                                      "determine the active state sequence"
                            accumulateVec = (
                                ISdivMatrix[:,0] -
                                np.log(1. / nbfaccomps)
                                )
                            antecedentMat = np.zeros([nbfaccomps,
                                                      self.nbFramesSigRepr],
                                                     dtype=np.int32)
                            for n in range(1, self.nbFramesSigRepr):
                                tmpMat = (
                                    np.vstack(accumulateVec) -
                                    np.log(factor['TW_DP_params'] + eps))
                                
                                antecedentMat[:,n] = (
                                    np.argmin(tmpMat, axis=0)
                                    )
                                accumulateVec += (
                                    tmpMat[antecedentMat[:,n],
                                           range(nbfaccomps)] + 
                                    ISdivMatrix[:,n]
                                    )
                                # to avoid overflow?
                                accumulateVec -= accumulateVec.min()
                            
                            del tmpMat
                            
                            active_state_seq = np.zeros(self.nbFramesSigRepr,
                                                        dtype=np.int32)
                            active_state_seq[-1] = np.argmin(accumulateVec)
                            for framenb in range(self.nbFramesSigRepr-1,0,-1):
                                active_state_seq[framenb-1] = (
                                    antecedentMat[active_state_seq[framenb],
                                                  framenb-1]
                                    )
                            
                        else:
                            raise NotImplementedError(
                                "No implementation for time constraint other "+
                                "than GMM, GSMM, HMM and SHMM")
                        
                        if self.verbose:
                            print "    Update Time Weights"
                            
                        factor['TW'][:] = 0.
                        for framenb in range(self.nbFramesSigRepr):
                            factor['TW'][active_state_seq[framenb],framenb] = (
                                factor['TW_all'][active_state_seq[framenb],
                                                 framenb]
                                )
                            
                        if factor['TW_DP_frdm_prior'] == 'free':
                            print "    Updating the transition probabilities"
                            if factor['TW_constr'] in ('GMM', 'GSMM'):
                                for compnb in range(nbfaccomps):
                                    factor['TW_DP_params'][compnb] = (
                                        np.sum(active_state_seq==compnb) * 1. /
                                        self.nbFramesSigRepr
                                        )
                            elif factor['TW_constr'] in ('HMM', 'SHMM'):
                                for prevstate in range(nbfaccomps):
                                    upd_den = np.sum(
                                        active_state_seq[:-1]==prevstate)
                                    if upd_den:
                                        for nextstate in range(nbfaccomps):
                                            upd_num = 1. * np.sum(
                                                (active_state_seq[:-1]==
                                                 prevstate) *
                                                (active_state_seq[1:]==
                                                 nextstate))
                                            factor['TW_DP_params'][prevstate,
                                                                   nextstate]=(
                                                upd_num / upd_den
                                                ) # TODO: check this part
                            else:
                                raise NotImplementedError(
                                    "Required time constraints not "+
                                    "implemented.")
                        
                # update TB = time basis
                if len(factor['TB']) and factor['TB_frdm_prior'] == 'free':
                    if self.verbose>1: print "    Updating Time basis"
                    spat_comp_power = (
                        np.maximum(
                            self.comp_spat_comp_power(
                                spat_comp_ind,
                                spec_comp_ind=[spec_comp_ind],),
                            eps)
                        )
                    W = (
                        np.dot(np.dot(factor['FB'], factor['FW']),
                               factor['TW'])
                        )
                    # denominator + correlation penalization
                    if self.lambdaCorr > 0:
                        corrPen = (
                            self.lambdaCorr
                            * np.maximum(spat_comp_pow_minus,# - spat_comp_power,
                                         eps)
                            / np.maximum(spat_comp_powers**2, eps)
                            )
                        ##if self.verbose>2:#DEBUG
                        ##    # pedantic :
                        ##    print corrPen.mean(), (1./spat_comp_power).mean()
                    else:
                        corrPen = 0.
                    comp_den = (
                        np.dot(W.T,
                               other_fact_power * 
                               (1. / spat_comp_power +
                                corrPen))
                        )
                    # numerator
                    if self.lambdaCorr > 0:# corrPen > 0:
                        corrPen *= 2 *(
                            spat_comp_power
                            / spat_comp_powers
                            )
                    comp_num = (
                        np.dot(W.T,
                               (hat_W[spat_comp_ind]
                                / np.maximum(spat_comp_power**2, eps)
                                + corrPen)
                               * other_fact_power)
                        )
                    factor['TB'] *= (
                        comp_num / np.maximum(comp_den, eps)) ** omega
                    del comp_num, comp_den, spat_comp_power, W
    
    def renormalize_parameters(self):
        """renormalize_parameters
        
        Re-normalize the components
        """
        if self.verbose>0:
            print "    re-normalizing components"
        pass
        if self.verbose>1:
            print "         normalizing spatial components..."
        # renormalize spatial components
        Kspat = len(self.spat_comps)
        spat_global_energy = np.zeros(Kspat)
        for spat_ind, spat_comp in self.spat_comps.items():
            spat_global_energy[spat_ind] = (
                np.mean (np.abs(spat_comp['params'])**2))
            spat_comp['params'] /= np.sqrt(spat_global_energy[spat_ind])
            
        if self.verbose>5:
            print "spat_global_energy", spat_global_energy
        
        # renormalize spectral components
        Kspec = len(self.spec_comps)
        for spec_ind, spec_comp in self.spec_comps.items():
            global_energy = spat_global_energy[spec_comp['spat_comp_ind']]
            
            nbfactors = len(spec_comp['factor'])
            
            for fact_ind, factor in spec_comp['factor'].items():
                factor['FB'] *= global_energy
                w = factor['FB'].max(axis=0)#.mean(axis=0)
                w[w==0] = 1.
                factor['FB'] /= w
                factor['FW'] *= np.vstack(w)
                
                if factor['TW_constr'] not in ('GMM', 'HMM'):
                    w = factor['FW'].mean(axis=0)
                    w[w==0] = 1.
                    factor['FW'] /= w
                    factor['TW'] *= np.vstack(w)
                    # Only testing this: in order to avoid
                    # big crash, if for one factor, everything in TW
                    # turns out to get 0, then "restart" it with random
                    if np.sum(factor['TW']) < eps:
                        factor['TW'] = np.random.randn(*factor['TW'].shape)**2
                        factor['TW'] *= 1e3 * eps # so it s not too small
                        if self.verbose:
                            print "    renorm: reinitialized TW for spec",
                            print spec_ind, "factor", fact_ind
                    if len(factor['TB']):
                        w = factor['TB'].mean(axis=1)
                        w[w==0] = 1.
                        factor['TB'] /= np.vstack(w)
                        factor['TW'] *= w
                        
                    global_energy = factor['TW'].mean()
                    if fact_ind < (nbfactors - 1):
                        factor['TW'] /= global_energy
                else:
                    raise NotImplementedError(
                        "Temporal discrete state mngmt not done yet. ")
            
    def setComponentParameter(self, newValue, spec_ind, fact_ind=0,
                              partLabel='FB', prior='free',
                              keepDimensions=True):
        """A helper function to set a
        self.spec_comp[spec_ind]['factor'][fact_ind][partLabel] to
        the given value.
        
        TODO 20130522 finish this function to make it general purpose...
        """
        ###### DEBUG #####
        print "NOT IMPLEMENTED YET, PLEASE SET THE COMPONENTS DIRECTLY"
        pass
        ###### DEBUG #####
        if keepDimenstions:
            if (newValue.shape !=
            self.spec_comp[spec_ind]['factor'][fact_ind][partLabel].shape):
                raise ValueError("the provided value does not have the correct"+
                                 " size:"+str(newValue.shape)+
                                 " instead of "+
                                 str(
                 self.spec_comp[spec_ind]['factor'][fact_ind][partLabel].shape))
            
        else:
            # nightmare of error checking for sizes... 
            if partLabel == 'FB':
                newShape = newValue.shape
                oldShape = self.spec_comp[
                    spec_ind]['factor'][fact_ind]['FB'].shape
                if newShape[0] != self.nbFreqsSigRepr:
                    raise ValueError("FB: cannot change dimension of "+
                                     "signal representation.")
                if newShape[1] != oldShape[1]:
                    if self.verbose:
                        print "    Changing the Freq Weights for FB:"
                        self.spec_comp[spec_ind]['factor'][fact_ind]['FB']
                self.spec_comp[spec_ind]['factor'][fact_ind]['FB'] = newValue
            elif partLabel == 'FW':
                pass
            elif partLabel == 'TW':
                pass
            elif partLabel == 'TB':
                pass
            else:
                raise ValueError("No such thing as "+
                                 partLabel+
                                 " in components!")
        self.spec_comp[spec_ind]['factor'][fact_ind][
            partLabel+'_frdm_prior'] = prior
                
    def initialize_all_spec_comps_with_NMF(self,
                                           sameInitAll=False,
                                           **kwargs):
        """Computes an NMF on the one-channel mix (averaging diagonal
        of self.Cx, which are the power spectra of the corresponding
        channel)

        .. math::
        
            C_x \\approx W H
        
        then, for all spec_comp in self.spec_comps, we set::
        
            spec_comp['FB'] = W
            spec_comp['TW'] = H
            
        
        """
        if sameInitAll:
            # initialize the components with the same parameters
            return self.initialize_all_spec_comps_with_NMF_same(**kwargs)
        else:
            # initialize the components with individual params,
            # in particular, initializing the NMF with the available
            # components (but only with factor 0)
            return self.initialize_all_spec_comps_with_NMF_indiv(**kwargs)

    def initialize_all_spec_comps_with_NMF_indiv(self, niter=10,
                                                 updateFreqBasis=True,
                                                 updateTimeWeight=True,
                                                 **kwargs):
        """initialize the spectral components with an NMF decomposition,
        with individual decomposition of the monophonic signal TF
        representation.

        TODO make keepFBind and keepTWind, in order to provide
        finer control on which indices are updated. Also requires
        a modified NMF decomposition function.
        
        """
        # list of the sizes of the 0th factors, of all components
        nbSpecComps = [spec_comp['factor'][0]['FB'].shape[1]
                       for spec_comp in self.spec_comps.values()]
        totalNMFComps = np.sum(nbSpecComps)
        
        # initializing the NMF FreqBasis (FB) and TimeWeight (TW)
        # with the corresponding quantities in self.spec_comps:
        FBinit = np.zeros([self.nbFreqsSigRepr, totalNMFComps])
        TWinit = np.zeros([totalNMFComps, self.nbFramesSigRepr])
        
        for spec_ind, spec_comp in self.spec_comps.items():
            ind_start = np.sum(nbSpecComps[:spec_ind])
            ind_stop = ind_start + nbSpecComps[spec_ind]
            FBinit[:,ind_start:ind_stop] = (
                spec_comp['factor'][0]['FB'])
            TWinit[ind_start:ind_stop] = (
                spec_comp['factor'][0]['TW'])
        
        # computing the monaural signal representation
        #     summing the contributions over all the channels:
        nc = self.audioObject.channels
        Cx = np.copy(np.real(self.Cx[0]))
        for chan in range(1, nc):
            # stored an "efficient" way, so index "complicated":
            index = np.sum(np.arange(nc, nc-chan, -1))
            Cx += np.real(self.Cx[index])
            
        Cx /= np.double(nc)
        
        W, H = NMF_decomp_init(SX=Cx, nbComps=totalNMFComps,
                               niter=niter, verbose=self.verbose,
                               Winit=FBinit, Hinit=TWinit,
                               updateW=updateFreqBasis,
                               updateH=updateTimeWeight)
        
        # copy the result in the corresponding spec_comps:
        for spec_ind, spec_comp in self.spec_comps.items():
            ind_start = np.sum(nbSpecComps[:spec_ind])
            ind_stop = ind_start + nbSpecComps[spec_ind]
            if updateFreqBasis:
                spec_comp['factor'][0]['FB'] = (
                    np.maximum(
                        W[:,ind_start:ind_stop],
                        eps)
                    )
            if updateTimeWeight:
                spec_comp['factor'][0]['TW'] = ( 
                    np.maximum(H[ind_start:ind_stop],eps))
                
        self.renormalize_parameters()
    
    def initialize_all_spec_comps_with_NMF_same(self, niter=10,
                                                **kwargs):
        """
        Initialize all the components with the same amplitude and spectral
        matrices `W` and `H`.
        """
        if not np.all([len(spec_comp['factor'])==1
                       for spec_comp in self.spec_comps.values()]):
            raise NotImplementedError(
                "NMF init not implemented for multi factor models.")
        
        nbSpecComps = [spec_comp['factor'][0]['FB'].shape[1]
                       for spec_comp in self.spec_comps.values()]
        nbComps = np.max(nbSpecComps)
        
        nc = self.audioObject.channels
        # computing the signal representation
        Cx = np.copy(np.real(self.Cx[0]))
        for chan in range(1, nc):
            # stored an "efficient" way, so index "complicated":
            index = np.sum(np.arange(nc, nc-chan, -1))
            Cx += np.real(self.Cx[index])
            
        Cx /= np.double(nc)
        
        # computing NMF of Cx:
        W, H = NMF_decomposition(SX=Cx, verbose=self.verbose,
                                 nbComps=nbComps, niter=niter)
        
        # reordering so that most energy in first components
        Hsum = H.sum(axis=1)
        indexSort = np.argsort(Hsum)[::-1]
        W = W[:,indexSort]
        H = H[indexSort]
        
        for spec_comp in self.spec_comps.values():
            ncomp = spec_comp['factor'][0]['FB'].shape[1]
            spec_comp['factor'][0]['FB'][:] = W[:, :ncomp]
            spec_comp['factor'][0]['TW'][:] = H[:ncomp]
        
        self.renormalize_parameters()
    
    def initializeConvParams(self, initMethod='demix'):
        """setting the spatial parameters
        """
        nc = self.audioObject.channels
        for spat_ind, spat_comp in self.spat_comps.items():
            if spat_comp['mix_type'] != 'inst':
                warnings.warn("Spatial component %d "%spat_ind+
                              "already not instantaneous, overwriting...")
            
            # spat_comp['time_dep'] = 'indep'
            spat_comp['mix_type'] = 'conv'
            # spat_comp['frdm_prior'] = 'free'
        
        if initMethod == 'demix':
            maxclusters = max(40, 10 * len(self.spat_comps))
            neighbours = 15
            
            # default for demix to work best: #FIXME!!!
            wlen = self.demixParams['wlen']# 20482048
            hopsize = self.demixParams['hopsize']#1024 
            
            demixInst = demix.DEMIX(
                audio=self.audioObject.filename,
                nsources=len(self.spat_comps), # spatial comps for demix
                wlen=wlen,
                hopsize=hopsize,
                neighbors=neighbours,
                verbose=self.verbose,
                maxclusters=maxclusters)
            
            demixInst.comp_pcafeatures()
            demixInst.comp_parameters()
            demixInst.init_subpts_set()
            demixInst.comp_clusters()
            demixInst.refine_clusters()
            
            # mixing parameters from DEMIX estimation:
            #     results in an nsrc x nfreqs x nc array
            A = demixInst.steeringVectorsFromCentroids()
            del demixInst
        elif 'rand' in initMethod:
            A = (
                np.random.randn(len(self.spat_comps),
                                self.nbFreqsSigRepr,
                                nc,)
                + 1j * np.random.randn(len(self.spat_comps),
                                       self.nbFreqsSigRepr,
                                       nc,)
                )
        else:
            raise ValueError("Init method not implemented.")
            
        # filling the spatial components:
        for nspat, (spat_ind, spat_comp) in enumerate(self.spat_comps.items()):
            spat_comp_param_inst = spat_comp['params']
            spat_comp['params'] = np.zeros([self.rank[nspat],
                                            nc,
                                            self.nbFreqsSigRepr],
                                           dtype=np.complex)
            for r in range(self.rank[nspat]):
                spat_comp['params'][r] = (
                    A[spat_ind].T
                    )
    
class MultiChanNMFInst_FASST(FASST):
    """MultiChanNMFInst_FASST
    
    sub-classes FASST
    
    This class implements the Multi-channel Non-Negative Matrix Factorisation
    (NMF) 
    """
    def __init__(self, audio,
                 nbComps=3, nbNMFComps=4,
                 spatial_rank=2,
                 **kwargs):
        """
        DESCRIPTION
        -----------
        
        
        ARGUMENTS
        ---------
        
        nbComps (int)
            The number of (spatial) components in FASST framework.
            
        nbNMFComps (int)
            The number of NMF components in each spatial component.
        """
        super(MultiChanNMFInst_FASST, self).__init__(audio=audio, **kwargs)
        self.comp_transf_Cx()
        
        self.nbComps = nbComps
        self.nbNMFComps = nbNMFComps
        self.rank = np.atleast_1d(spatial_rank)
        if self.rank.size < self.nbComps:
            self.rank = [self.rank[0],] * self.nbComps
        
        self._initialize_structures()
    
    def _initialize_structures(self): #, nbComps, nbNMFComps, spatial_rank):
        nc = self.audioObject.channels
        
        self.spat_comps = {}
        self.spec_comps = {}
        for j in range(self.nbComps):
            # initialize the spatial component
            self.spat_comps[j] = {}
            self.spat_comps[j]['time_dep'] = 'indep'
            self.spat_comps[j]['mix_type'] = 'inst'
            self.spat_comps[j]['frdm_prior'] = 'free'
            self.spat_comps[j]['params'] = np.random.randn(nc, self.rank[j])
            if nc == 2: # spreading the sources evenly for init on stereo
                self.spat_comps[j]['params'] = (
                    np.array([np.sin((j+1) * np.pi / (2.*(self.nbComps + 1))) +
                              np.random.randn(self.rank[j])*np.sqrt(0.01),
                              np.cos((j+1) * np.pi / (2.*(self.nbComps + 1))) +
                              np.random.randn(self.rank[j])*np.sqrt(0.01)]))
            
            # initialize single factor spectral component
            self.spec_comps[j] = {}
            self.spec_comps[j]['spat_comp_ind'] = j
            self.spec_comps[j]['factor'] = {}
            self.spec_comps[j]['factor'][0] = {}
            self.spec_comps[j]['factor'][0]['FB'] = (
                0.75 * np.abs(np.random.randn(self.nbFreqsSigRepr,
                                              self.nbNMFComps)) +
                0.25)
            self.spec_comps[j]['factor'][0]['FW'] = (
                np.eye(self.nbNMFComps))
            self.spec_comps[j]['factor'][0]['TW'] = (
                0.75 * np.abs(np.random.randn(self.nbNMFComps,
                                              self.nbFramesSigRepr)) +
                0.25)
            self.spec_comps[j]['factor'][0]['TB'] = []
            self.spec_comps[j]['factor'][0]['FB_frdm_prior'] = 'free'
            self.spec_comps[j]['factor'][0]['FW_frdm_prior'] = 'fixed'
            self.spec_comps[j]['factor'][0]['TW_frdm_prior'] = 'free'
            self.spec_comps[j]['factor'][0]['TB_frdm_prior'] = []
            self.spec_comps[j]['factor'][0]['TW_constr'] = 'NMF'
            
        self.renormalize_parameters()
        
    def setSpecCompFB(self, compNb, FB, FB_frdm_prior='fixed'):
        """SetSpecCompFB
        
        sets the spectral component's frequency basis.
        
        """
        speccomp = self.spec_comps[compNb]['factor'][0]
        if self.nbFreqsSigRepr != FB.shape[0]:
            raise AttributeError("Size of provided FB is not consistent"+
                                 " with inner attributes")
        speccomp['FB'] = np.copy(FB)
        ncomp = FB.shape[1]
        
        speccomp['FW'] = np.eye(ncomp)
        speccomp['TW'] = (
                0.75 * np.abs(np.random.randn(ncomp,
                                              self.nbFramesSigRepr)) +
                0.25)
        speccomp['FB_frdm_prior'] = FB_frdm_prior

class MultiChanNMFConv(MultiChanNMFInst_FASST):
    """Takes the multichannel NMF instantaneous class, and makes it
    convolutive!
    """
    def __init__(self, audio,
                 nbComps=3, nbNMFComps=4,
                 spatial_rank=2,
                 **kwargs):
        super(MultiChanNMFConv, self).__init__(audio=audio,
                                               nbComps=nbComps,
                                               nbNMFComps=nbNMFComps,
                                               spatial_rank=spatial_rank,
                                               **kwargs)
        # self.makeItConvolutive()
        # DIY: upgrade to convolutive after a few instantaneous, maybe? 
        
    def makeItConvolutive(self):
        nc = self.audioObject.channels
        for nspat, (spat_ind, spat_comp) in enumerate(self.spat_comps.items()):
            if spat_comp['mix_type'] != 'inst':
                warnings.warn("Spatial component %d "%spat_ind+
                              "already not instantaneous, skipping...")
            else:
                # spat_comp['time_dep'] = 'indep'
                spat_comp['mix_type'] = 'conv'
                # spat_comp['frdm_prior'] = 'free'
                spat_comp_param_inst = spat_comp['params']
                spat_comp['params'] = np.zeros([self.rank[nspat],
                                                nc,
                                                self.nbFreqsSigRepr],
                                               dtype=np.complex)
                for f in range(self.nbFreqsSigRepr):
                    spat_comp['params'][:,:,f] = spat_comp_param_inst.T

class MultiChanHMM(MultiChanNMFConv):
    def __init__(self, audio,
                 nbComps=3, nbNMFComps=4,
                 spatial_rank=2,
                 **kwargs):
        super(MultiChanHMM, self).__init__(audio=audio,
                                               nbComps=nbComps,
                                               nbNMFComps=nbNMFComps,
                                               spatial_rank=spatial_rank,
                                               **kwargs)
        
    def makeItHMM(self):
        """
        Turns the required parameters into HMM time constraints
        """
        for spec_ind, spec_comp in self.spec_comps.items():
            for fac_ind, factor in spec_comp['factor'].items():
                factor['TW_constr'] = 'HMM'
                factor['TW_DP_frdm_prior'] = 'free'
    
    def makeItSHMM(self):
        """
        Turns the required parameters into SHMM time constraints
        """
        for spec_ind, spec_comp in self.spec_comps.items():
            for fac_ind, factor in spec_comp['factor'].items():
                nbfaccomps = factor['TW'].shape[0]
                factor['TW_constr'] = 'SHMM'
                factor['TW_DP_params'] = (
                    9 * np.eye( nbfaccomps)
                    )
                factor['TW_DP_params'] += 1.
                factor['TW_DP_params'] /= (
                    np.vstack(factor['TW_DP_params'].sum(axis=1)))
                factor['TW_DP_frdm_prior'] = 'fixed'
                # factor['TW_DP_frdm_prior'] = 'free'
        
class multiChanSourceF0Filter(FASST):
    """multi channel source/filter model
    nbcomps components, nbcomps-1 SF models, 1 residual component
    
    """
    def __init__(self, audio,
                 nbComps=3, 
                 nbNMFResComps=1, 
                 nbFilterComps=20, 
                 nbFilterWeigs=[4,], 
                 minF0=39, maxF0=2000, minF0search=80, maxF0search=800,
                 stepnoteF0=16, chirpPerF0=1, 
                 spatial_rank=1,
                 sparsity=None,
                 **kwargs):
        """
        DESCRIPTION
        -----------
        __init__(self, audio,
                 nbComps=3, ## nb of components
                 nbNMFResComps=3, ## nb of residual components
                 nbFilterComps=20, ## nb of filter components
                 nbFilterWeigs=4, ## nb of filter components
                 minF0=80, maxF0=800, ## range for comb spectra
                 stepnoteF0=4, chirpPerF0=1, 
                 spatial_rank=1,
                 sparsity=None,
                 **kwargs)
        
        ARGUMENTS
        ---------
        
        nbComps (int)
            The number of (spatial) components in FASST framework.
            
        nbNMFComps (int)
            The number of NMF components in each spatial component.
            
        sparsity (list of size 1 or nbComps)
            
        
        """
        super(multiChanSourceF0Filter, self).__init__(audio=audio, **kwargs)
        self.comp_transf_Cx()
        self.sourceParams = {'minF0': minF0,
                             'maxF0': maxF0,
                             'stepnoteF0': stepnoteF0,
                             'chirpPerF0': chirpPerF0,
                             'minF0search': minF0search,
                             'maxF0search': maxF0search,}
                             # __c quoi ca...__ 'chirpPerF02072': chirpPerF0}
        self.nbComps = nbComps
        self.nbNMFResComps = nbNMFResComps
        self.nbFilterComps = nbFilterComps
        if len(nbFilterWeigs) < self.nbComps - 1:
            self.nbFilterWeigs = [nbFilterWeigs[0],] * self.nbComps
        else:
            self.nbFilterWeigs = nbFilterWeigs
            
        # initialize the spatial_ranks, reformating here.
        # 20130611 TODO check that it does not break too much everywhere!
        self.spatial_rank = np.atleast_1d(spatial_rank)
        if self.spatial_rank.size < self.nbComps:
            self.spatial_rank = [self.spatial_rank[0],] * self.nbComps
        
        # the source dictionary is shared among all the components,
        # so storing it one for all:
        self.F0Table, WF0, trfoBis = (
            #generate_WF0_chirped(minF0, maxF0,
            #                     Fs=self.audioObject.samplerate,
            #                     Nfft=self.sig_repr_params['fsize'],
            #                     stepNotes=stepnoteF0,
            #                     lengthWindow=self.sig_repr_params['wlen'],
            #                     Ot=0.5,
            #                     perF0=chirpPerF0,
            #                     depthChirpInSemiTone=0.5,
            #                     loadWF0=True,
            #                     analysisWindow='hanning')
            SLS.slf.generate_WF0_TR_chirped(
                transform=self.tft,
                minF0=minF0, maxF0=maxF0,
                stepNotes=stepnoteF0,
                Ot=0.5, perF0=chirpPerF0, 
                depthChirpInSemiTone=0.5, loadWF0=True,
                verbose=self.verbose,)
            )
        
        # removing patterns in low energy bins - setting to eps:
        for nwf0comp in range(WF0.shape[1]): 
            indLowEnergy = np.where(WF0[:,nwf0comp]<WF0[:,nwf0comp].max()*1e-4)
            WF0[indLowEnergy, nwf0comp] = eps
        self.sourceFreqComps = (
            np.ascontiguousarray(
            np.hstack([WF0[:self.nbFreqsSigRepr],
                       np.vstack(np.ones(self.nbFreqsSigRepr))]))
            )
        del WF0
        self.nbSourceComps = self.sourceFreqComps.shape[1]
        self.sourceFreqWeights = np.eye(self.nbSourceComps)
        # ... and the same for the filter part
        self.filterFreqComps = (
            generateHannBasis(
                numberFrequencyBins=self.nbFreqsSigRepr,
                sizeOfFourier=self.sig_repr_params['fsize'],
                Fs=self.audioObject.samplerate,
                frequencyScale='linear',
                numberOfBasis=self.nbFilterComps)
            )
        self.sparsity = sparsity
        self._initialize_structures()
    
    def _initialize_structures(self):
        self.rank = self.spatial_rank
        nc = self.audioObject.channels
        sparsity = self.sparsity
        
        self.spat_comps = {}
        self.spec_comps = {}
        for j in range(self.nbComps - 1):
            # initialize the spatial component
            self.spat_comps[j] = {}
            self.spat_comps[j]['time_dep'] = 'indep'
            self.spat_comps[j]['mix_type'] = 'inst'
            self.spat_comps[j]['frdm_prior'] = 'free'
            self.spat_comps[j]['params'] = np.random.randn(nc, self.rank[j])
            if nc == 2: # spreading the sources evenly for init on stereo
                self.spat_comps[j]['params'] = (
                    np.array([np.sin((j+1) * np.pi / (2.*(self.nbComps))) +
                              np.random.randn(self.rank[j])*np.sqrt(0.01),
                              np.cos((j+1) * np.pi / (2.*(self.nbComps))) +
                              np.random.randn(self.rank[j])*np.sqrt(0.01)]))
            
            # initialize source factor spectral component
            self.spec_comps[j] = {}
            self.spec_comps[j]['spat_comp_ind'] = j
            self.spec_comps[j]['factor'] = {}
            self.spec_comps[j]['factor'][0] = {}
            self.spec_comps[j]['factor'][0]['FB'] = self.sourceFreqComps
            self.spec_comps[j]['factor'][0]['FW'] = self.sourceFreqWeights
            self.spec_comps[j]['factor'][0]['TW'] = (
                0.75 * np.abs(np.random.randn(self.nbSourceComps,
                                              self.nbFramesSigRepr)) +
                0.25)
            self.spec_comps[j]['factor'][0]['TB'] = []
            self.spec_comps[j]['factor'][0]['FB_frdm_prior'] = 'fixed'
            self.spec_comps[j]['factor'][0]['FW_frdm_prior'] = 'fixed'
            self.spec_comps[j]['factor'][0]['TW_frdm_prior'] = 'free'
            self.spec_comps[j]['factor'][0]['TB_frdm_prior'] = []
            self.spec_comps[j]['factor'][0]['TW_constr'] = 'NMF'
            
            # initialize filter factor spectral components
            self.spec_comps[j]['factor'][1] = {}
            self.spec_comps[j]['factor'][1]['FB'] = self.filterFreqComps
            self.spec_comps[j]['factor'][1]['FW'] = (
                0.75 * np.abs(np.random.randn(self.nbFilterComps,
                                              self.nbFilterWeigs[j])) +
                0.25)
            self.spec_comps[j]['factor'][1]['TW'] = (
                0.75 * np.abs(np.random.randn(self.nbFilterWeigs[j],
                                              self.nbFramesSigRepr)) +
                0.25)
            self.spec_comps[j]['factor'][1]['TB'] = []
            self.spec_comps[j]['factor'][1]['FB_frdm_prior'] = 'fixed'
            self.spec_comps[j]['factor'][1]['FW_frdm_prior'] = 'free'
            self.spec_comps[j]['factor'][1]['TW_frdm_prior'] = 'free'
            self.spec_comps[j]['factor'][1]['TB_frdm_prior'] = []
            self.spec_comps[j]['factor'][1]['TW_constr'] = 'NMF'
            
        # residual component:
        self.resSpatialRank = self.rank[-1]#2
        j = self.nbComps - 1
        # initialize the spatial component
        self.spat_comps[j] = {}
        self.spat_comps[j]['time_dep'] = 'indep'
        self.spat_comps[j]['mix_type'] = 'inst'
        self.spat_comps[j]['frdm_prior'] = 'free'
        self.spat_comps[j]['params'] = np.random.randn(nc, self.resSpatialRank)
        # 20120920 trying no initialization for residual:
        ##if nc == 2: # spreading the sources evenly for init on stereo
        ##    self.spat_comps[j]['params'] = (
        ##        np.array([np.sin((j+1) * np.pi / (2.*(self.nbComps + 1))) +
        ##                np.random.randn(self.resSpatialRank)*np.sqrt(0.01),
        ##                np.cos((j+1) * np.pi / (2.*(self.nbComps + 1))) +
        ##                np.random.randn(self.resSpatialRank)*np.sqrt(0.01)]))
            
        # initialize single factor spectral component
        self.spec_comps[j] = {}
        self.spec_comps[j]['spat_comp_ind'] = j
        self.spec_comps[j]['factor'] = {}
        self.spec_comps[j]['factor'][0] = {}
        self.spec_comps[j]['factor'][0]['FB'] = (
            0.75 * np.abs(np.random.randn(self.nbFreqsSigRepr,
                                          self.nbNMFResComps)) +
            0.25)
        self.spec_comps[j]['factor'][0]['FW'] = (
            np.eye(self.nbNMFResComps))
        self.spec_comps[j]['factor'][0]['TW'] = (
            0.75 * np.abs(np.random.randn(self.nbNMFResComps,
                                          self.nbFramesSigRepr)) +
            0.25)
        self.spec_comps[j]['factor'][0]['TB'] = []
        self.spec_comps[j]['factor'][0]['FB_frdm_prior'] = 'free'
        self.spec_comps[j]['factor'][0]['FW_frdm_prior'] = 'fixed'
        self.spec_comps[j]['factor'][0]['TW_frdm_prior'] = 'free'
        self.spec_comps[j]['factor'][0]['TB_frdm_prior'] = []
        self.spec_comps[j]['factor'][0]['TW_constr'] = 'NMF'
        
        if sparsity is None or len(sparsity) not in (1, self.nbComps):
            for j in range(self.nbComps):
                self.spec_comps[j]['sparsity'] = False
        elif len(sparsity) == self.nbComps:
            # sparsity induces a "sparse" activation of
            # self.spec_comps[j]['factor'][0]['TW'], that is,
            # the time weights for the source part.
            # This is implemented as in:
            # Durrieu, J.-L. & Thiran, J.-P.
            #    Sparse Non-Negative Decomposition Of Speech Power Spectra For
            #    Formant Tracking
            # in proc. of the IEEE International Conference on Acoustics,
            # Speech and Signal Processing, Pragues, Czech Republic, 2011.
            #
            # This means that at each GEM iteration, the TW coefficients
            # are further shrinked down to be concentrating around a
            # single component (a single F0 in SF model)
            for j in range(self.nbComps):
                self.spec_comps[j]['sparsity'] = sparsity[j]
        else:
            for j in range(self.nbComps):
                self.spec_comps[j]['sparsity'] = sparsity[0]
        
        self.renormalize_parameters()
        
    def initSpecCompsWithLabelAndFiles(self, instrus=[], instru2modelfile={},
                                       freqBasisAdaptive='fixed'):
        """Initialize the spectral components with the instrument labels as
        well as with the components stored in the provided dictionary in
        `instru2modelfile`
        
        `instrus` is a list with labels:
            `'SourceFilter'`: keep the intialized source filter model
            `'Free_<nb_comp>'`: initialize the model with an adaptable
                spectral component using `nb_comp` elements in the NMF
                frequency basis
            `<key_in_instru2modelfile>`: initialize with the :py:class:GSMM
                available and stored in the archive npz with filename
                `instru2modelfile[key_in_instru2modelfile]`
                
        NB: needs the gmm-gsmm module to be installed and in the pythonpath
        """
        instrumentNames = {}
        for n, i in enumerate(instrus):
            instrumentNames[n] = i
            if i == 'SourceFilter':
                self.spec_comps[n]['label'] = i
                print "    Source", n, "left as general Source-Filter model."
            elif 'Free' in i: # assumes Free_nbNMFComps
                nbNMFComps = int(i.split('_')[-1])
                print "    Source", n, "set as free NMF source."
                # initialize single factor spectral component
                self.spec_comps[n] = {}
                self.spec_comps[n]['label'] = i
                self.spec_comps[n]['spat_comp_ind'] = n
                self.spec_comps[n]['factor'] = {}
                self.spec_comps[n]['factor'][0] = {}
                self.spec_comps[n]['factor'][0]['FB'] = (
                    0.75 * np.abs(np.random.randn(self.nbFreqsSigRepr,
                                                  nbNMFComps)) +
                    0.25)
                self.spec_comps[n]['factor'][0]['FW'] = (
                    np.eye(nbNMFComps))
                self.spec_comps[n]['factor'][0]['TW'] = (
                    0.75 * np.abs(np.random.randn(nbNMFComps,
                                                  self.nbFramesSigRepr)) +
                    0.25)
                self.spec_comps[n]['factor'][0]['TB'] = []
                self.spec_comps[n]['factor'][0]['FB_frdm_prior'] = 'free'
                self.spec_comps[n]['factor'][0]['FW_frdm_prior'] = 'fixed'
                self.spec_comps[n]['factor'][0]['TW_frdm_prior'] = 'free'
                self.spec_comps[n]['factor'][0]['TB_frdm_prior'] = []
                self.spec_comps[n]['factor'][0]['TW_constr'] = 'NMF'
                # sparsity stuff
                sparsity = self.sparsity
                if sparsity is None or len(sparsity) not in (1, self.nbComps):
                    self.spec_comps[n]['sparsity'] = False
                elif len(sparsity) == self.nbComps:
                    self.spec_comps[n]['sparsity'] = sparsity[n]
                else:
                    self.spec_comps[n]['sparsity'] = sparsity[0]
            else: #if i != 'SourceFilter':
                print "    Source", n, "is", i
                modelfile = instru2modelfile[i]
                struc = np.load(modelfile)
                gsmm = struc['gsmm'].tolist()
                # Keeping only spectra that are not flat:
                decisionSpectra = np.any(np.diff(gsmm.sigw, axis=1)!=0, axis=1)
                # keeping only the spectra with enough weight:
                #     hard decision, remove all spectra with w == min(w)
                # decisionOnWeight = np.where(gsmm.w!=gsmm.w.min())[0]
                #     harder decision: remove all with w under a threshold:
                decisionOnWeight = (gsmm.w > gsmm.w.max()*1e-3)
                
                keepIndex = np.where(decisionSpectra+decisionOnWeight)[0]
                
                FB = np.ascontiguousarray(gsmm.sigw[keepIndex].T)
                #self.setSpecCompFB(compNb=n, FB=FB, FB_frdm_prior='fixed')
                self.setSpecCompFB(compNb=n, FB=FB,
                                   FB_frdm_prior=freqBasisAdaptive)
                self.spec_comps[n]['label'] = i
                struc.close()
        
        return instrumentNames
        
    def setSpecCompFB(self, compNb, FB, FB_frdm_prior='fixed',):
        """SetSpecCompFB
        
        sets the spectral component's frequency basis.
        
        """
        speccomp = self.spec_comps[compNb]['factor'][0]
        if self.nbFreqsSigRepr != FB.shape[0]:
            raise AttributeError("Size of provided FB is not consistent"+
                                 " with inner attributes")
        speccomp['FB'] = np.copy(FB)
        ncomp = FB.shape[1]
        
        speccomp['FW'] = np.eye(ncomp)
        speccomp['TW'] = (
                0.75 * np.abs(np.random.randn(ncomp,
                                              self.nbFramesSigRepr)) +
                0.25)
        speccomp['FB_frdm_prior'] = FB_frdm_prior
    
    def initializeFreeMats(self, niter=10):
        """initialize free matrices, with NMF decomposition
        """
        # we initialize the matrices with NMF decomposition using the
        # source matrix as basis W, the residual is left uninitialized
        nc = self.audioObject.channels
        # computing the signal representation
        Cx = np.copy(np.real(self.Cx[0]))
        for chan in range(1, nc):
            # stored an "efficient" way, so index "complicated":
            index = np.sum(np.arange(nc, nc-chan, -1))
            Cx += np.real(self.Cx[index])
        
        Cx /= np.double(nc)
        
        # computing NMF of Cx:
        W, H = NMF_decomp_init(SX=Cx,
                               Winit=np.dot(
                                   self.sourceFreqComps,
                                   self.spec_comps[0]['factor'][0]['FW']),
                               verbose=self.verbose,
                               nbComps=self.nbSourceComps,
                               niter=niter,
                               updateW=False, updateH=True,
                               )
        ##W, H, WFilt, HFilt = SFNMF_decomp_init(
        ##    SX=Cx,
        ##    nbComps=self.nbSourceComps,
        ##    nbFiltComps=self.nbFilterComps,
        ##    niter=niter, verbose=self.verbose,
        ##    Winit=,
        ##    Hinit=None,
        ##    WFiltInit=self.filterFreqComps,
        ##    HFiltInit=None,
        ##    updateW=False, updateH=True,
        ##    updateWFilt=False, updateHFilt=True)
        
        for ncomp in range(self.nbComps-1):
            spec_comp = self.spec_comps[ncomp]
            spec_comp['factor'][0]['TW'][:] = np.copy(H) / (self.nbComps-1)
            
        self.renormalize_parameters()
    
    def makeItConvolutive(self):
        """Takes the spatial parameters and sets them to a convolutive
        mixture, in case the parameter has not yet been changed to
        'conv' mode.
        """
        nc = self.audioObject.channels
        for nspat, (spat_ind, spat_comp) in enumerate(self.spat_comps.items()):
            if spat_comp['mix_type'] != 'inst':
                warnings.warn("Spatial component %d "%spat_ind+
                              "already not instantaneous, skipping...")
            else:
                # spat_comp['time_dep'] = 'indep'
                spat_comp['mix_type'] = 'conv'
                # spat_comp['frdm_prior'] = 'free'
                spat_comp_param_inst = spat_comp['params']
                spat_comp['params'] = np.zeros([self.rank[nspat],
                                                nc,
                                                self.nbFreqsSigRepr],
                                               dtype=np.complex)
                for f in range(self.nbFreqsSigRepr):
                    spat_comp['params'][:,:,f] = (
                        np.atleast_2d(spat_comp_param_inst.T))
                    
##    def initializeConvParams(self, initMethod='demix'):
##        """setting the spatial parameters
##        """
##        nc = self.audioObject.channels
##        for spat_ind, spat_comp in self.spat_comps.items():
##            if spat_comp['mix_type'] != 'inst':
##                warnings.warn("Spatial component %d "%spat_ind+
##                              "already not instantaneous, overwriting...")
            
##            # spat_comp['time_dep'] = 'indep'
##            spat_comp['mix_type'] = 'conv'
##            # spat_comp['frdm_prior'] = 'free'
        
##        if initMethod == 'demix':
##            maxclusters = max(40, 10 * len(self.spat_comps))
##            neighbours = 15
            
##            # default for demix to work best: #FIXME!!!
##            wlen = self.demixParams['wlen']# 2048
##            hopsize = self.demixParams['hopsize']
            
##            demixInst = demix.DEMIX(
##                audio=self.audioObject.filename,
##                nsources=len(self.spat_comps), # spatial comps for demix
##                #wlen=wlen,
##                #hopsize=hopsize,
##                #neighbors=neighbours,
##                verbose=self.verbose,
##                maxclusters=maxclusters,
##                **self.demixParams)
            
##            demixInst.comp_pcafeatures()
##            demixInst.comp_parameters()
##            demixInst.init_subpts_set()
##            demixInst.comp_clusters()
##            demixInst.refine_clusters()
            
##            # mixing parameters from DEMIX estimation:
##            #     results in an nsrc x nfreqs x nc array
##            A = demixInst.steeringVectorsFromCentroids()
##            del demixInst
##        elif 'rand' in initMethod:
##            A = (
##                np.random.randn(self.rank,
##                                self.nbFreqsSigRepr,
##                                nc,)
##                + 1j * np.random.randn(self.rank,
##                                self.nbFreqsSigRepr,
##                                nc,)
##                )
##        else:
##            raise ValueError("Init method not implemented.")
            
##        # filling the spatial components:
##        for spat_ind, spat_comp in self.spat_comps.items():
##            spat_comp_param_inst = spat_comp['params']
##            spat_comp['params'] = np.zeros([self.rank,
##                                            nc,
##                                            self.nbFreqsSigRepr],
##                                           dtype=np.complex)
##            for r in range(self.rank):
##                spat_comp['params'][r] = (
##                    A[spat_ind].T
##                    )
    
    def estim_param_a_post_model(self,):
        """estim_param_a_post_model
        
        Estimation of model parameters, using the sparsity constraints.
        """
        
        logSigma0 = np.log(np.max([spec['factor'][0]['TW'].shape[0]
                                   for spec in self.spec_comps.values()])**2)
        logSigmaInf = np.log(9.0)
        
        logliks = np.ones(self.iter_num)
        
        if self.noise['sim_ann_opt'] in ['ann', ]:
            self.noise['PSD'] = self.noise['ann_PSD_lim'][0]
        elif self.noise['sim_ann_opt'] is 'no_ann':
            self.noise['PSD'] = self.noise['ann_PSD_lim'][1]
        else:
            warnings.warn("To add noise to the signal, provide the "+
                          "sim_ann_opt from any of 'ann', "+
                          "'no_ann' or 'ann_ns_inj' ")
            
        for i in range(self.iter_num):
            if self.verbose:
                print "Iteration", i+1, "on", self.iter_num
            # adding the noise psd if required:
            if self.noise['sim_ann_opt'] in ['ann', 'ann_ns_inj']:
                self.noise['PSD'] = (
                    (np.sqrt(self.noise['ann_PSD_lim'][0]) *
                     (self.iter_num - i) +
                     np.sqrt(self.noise['ann_PSD_lim'][1]) * i) /
                    self.iter_num) ** 2
                
            # running the GEM iteration:
            logliks[i] = self.GEM_iteration()
            if self.verbose:
                print "    log-likelihood:", logliks[i]
                if i>0:
                    print "        improvement:", logliks[i]-logliks[i-1]
                    
            # sparsity
            sigma = np.exp(logSigma0 +
                           (logSigmaInf - 
                            logSigma0) / 
                           max(self.iter_num - 1.0, 1.) * i)
            self.reweigh_sparsity_constraint(sigma)
            
        return logliks
    
    def reweigh_sparsity_constraint(self, sigma):
        """reweigh_sparsity_constraint
        """
        if self.verbose>1:
            print "reweigh_sparsity_constraint:"
            print "    sigma", sigma
        for j in range(self.nbComps):
            spec_comp = self.spec_comps[j]
            if spec_comp['sparsity'] and \
                   spec_comp['factor'][0]['TW'].shape[0]>2:
                TW = spec_comp['factor'][0]['TW']
                K = TW.shape[0]
                # barycenter from energy of factor 0 TW component
                muTW = (
                    np.dot(np.arange(K - 1) * 
                           (np.arange(K - 1, 0, -1))**2, 
                           TW[:-1,:]) / 
                    np.dot((np.arange(K - 1, 0, -1))**2,
                           np.maximum(TW[:-1,:], eps))
                    )
                # smoothing the sequence:
                muTW  = st.medianFilter(muTW, length=spec_comp['sparsity'])
                if self.verbose>1:
                    print "        muTW NaNs in comp %d:" %j,
                    print np.any(np.isnan(muTW))
                
                twmask = (
                    np.exp(- 0.5 *
                           ((np.vstack(np.arange(K)) - muTW)**2) /
                           sigma)
                    )
                twmask[-1] = twmask.max(axis=0)
                twmask[:,twmask[-1]>0] /= twmask[-1][twmask[-1]>0]
                TW *= twmask

class multichanLead(multiChanSourceF0Filter):
    def __init__(self, *args, **kwargs):
        """multichanLead
        
        subclasses multiChanSourceF0Filter
        
        Provides additional methods to estimate the lead/accompaniment parameters
        meant to be used as initial parameters for one of the sources.
        
        Tentative plan for estimation:
        ## estimate the Lead/Accompaniment using SIMM
        ## estimate the spatial parameters for each of the separated signals
        ## plug the SIMM params and the spatial params into pyFASST, and
        ## re-estimate
        ## write the estimated signals and enjoy success!
        """
        super(multichanLead, self).__init__(*args, **kwargs)
        # removing some data from the object, recomputing when needed:
        del self.Cx
        del self.spat_comps
        ##del self.spec_comps
        
    def runDecomp(self, instrus=[],
                  instru2modelfile={},
                  dir_results='tmp/', maxFrames=4000,
                  niter_nmf=20, niter_simm=30):
        """Running the scheme that should make me famous.
        """
        # running some checks that the input is alright:
        for i in instrus:
            if not(i=='SourceFilter' or
                   i in instru2modelfile or
                   i.startswith("Free_")):
                raise ValueError('Instrument %s not known.' %i)
        
        # just running everything in __init__:
        # estimating the separated 
        self.estimSUIMM(maxFrames=maxFrames,
                        dir_results=dir_results,
                        simmIterNum=niter_simm)
        
        ##############
        # entering vacuum of nightmare of research trial and errors...
        # thus expect many undesirable commented lines...
        
        # putting everything in the right containers:
        self.comp_transf_Cx()
        self._initialize_structures()
        self.makeItConvolutive()
        
        # running DEMIX:
        ## 20130604 no need anymore, only for ALead:
        ALead, AAccp = self.demixOnSepSIMM(unvoiced=True)
        #   spatial components:
        #    accompaniment parameters:
        ## THE FOLLOWING SEEMS TO LEAD TO ISSUES and results not so good...
        ## 20130604 do this after initialize with NMF...
        ## for j in range(1, self.nbComps-1):
        ##     for r in range(self.rank):
        ##       ## the following assumes the instruments are sorted in the
        ##       ## right order, but we still need to think about that !
        ##       # self.spat_comps[j]['params'][r][:,:] = AAccp[j-1].T
        ##       # so for now, we just go for the sum of all the mixing params
        ##       self.spat_comps[j]['params'][r][:,:] = AAccp.sum(axis=0).T
        ## Trying randomized init:
        self.initializeConvParams(initMethod='rand')
        #    no modif for noise component...
        #    lead instrument spatial mat:
        for r in range(self.rank[0]):
            self.spat_comps[0]['params'][r][:,:] = ALead[0].T
        
        #   spectral components:
        
        ## Using the instrument models to initialize the matrices:
        # For convenience, we do this in a separate method:
        instrumentNames = self.initSpecCompsWithLabelAndFiles(
            instrus=instrus,
            instru2modelfile=instru2modelfile,
            freqBasisAdaptive='fixed')
        ## instrumentNames = {}
        ## for n, i in enumerate(instrus):
        ##     instrumentNames[n] = i
        ##     if i == 'SourceFilter':
        ##         print "    Source", n, "left as general Source-Filter model."
        ##     elif 'Free' in i: # assumes Free_nbNMFComps
        ##         nbNMFComps = int(i.split('_')[-1])
        ##         print "    Source", n, "set as free NMF source."
        ##         # initialize single factor spectral component
        ##         self.spec_comps[n] = {}
        ##         self.spec_comps[n]['spat_comp_ind'] = n
        ##         self.spec_comps[n]['factor'] = {}
        ##         self.spec_comps[n]['factor'][0] = {}
        ##         self.spec_comps[n]['factor'][0]['FB'] = (
        ##             0.75 * np.abs(np.random.randn(self.nbFreqsSigRepr,
        ##                                           nbNMFComps)) +
        ##             0.25)
        ##         self.spec_comps[n]['factor'][0]['FW'] = (
        ##             np.eye(nbNMFComps))
        ##         self.spec_comps[n]['factor'][0]['TW'] = (
        ##             0.75 * np.abs(np.random.randn(nbNMFComps,
        ##                                           self.nbFramesSigRepr)) +
        ##             0.25)
        ##         self.spec_comps[n]['factor'][0]['TB'] = []
        ##         self.spec_comps[n]['factor'][0]['FB_frdm_prior'] = 'free'
        ##         self.spec_comps[n]['factor'][0]['FW_frdm_prior'] = 'fixed'
        ##         self.spec_comps[n]['factor'][0]['TW_frdm_prior'] = 'free'
        ##         self.spec_comps[n]['factor'][0]['TB_frdm_prior'] = []
        ##         self.spec_comps[n]['factor'][0]['TW_constr'] = 'NMF'
        ##         # sparsity stuff
        ##         sparsity = self.sparsity
        ##         if sparsity is None or len(sparsity) not in (1, self.nbComps):
        ##             self.spec_comps[n]['sparsity'] = False
        ##         elif len(sparsity) == self.nbComps:
        ##             self.spec_comps[n]['sparsity'] = sparsity[n]
        ##         else:
        ##             self.spec_comps[n]['sparsity'] = sparsity[0]
        ##     else: #if i != 'SourceFilter':
        ##         print "    Source", n, "is", i
        ##         modelfile = instru2modelfile[i]
        ##         struc = np.load(modelfile)
        ##         gsmm = struc['gsmm'].tolist()
        ##         # Keeping only spectra that are not flat:
        ##         decisionSpectra = np.any(np.diff(gsmm.sigw, axis=1)!=0, axis=1)
        ##         # keeping only the spectra with enough weight:
        ##         #     hard decision, remove all spectra with w == min(w)
        ##         # decisionOnWeight = np.where(gsmm.w!=gsmm.w.min())[0]
        ##         #     harder decision: remove all with w under a threshold:
        ##         decisionOnWeight = (gsmm.w > gsmm.w.max()*1e-3)
        ##         
        ##         keepIndex = np.where(decisionSpectra+decisionOnWeight)[0]
        ##         
        ##         FB = np.ascontiguousarray(gsmm.sigw[keepIndex].T)
        ##         #self.setSpecCompFB(compNb=n, FB=FB, FB_frdm_prior='fixed')
        ##         self.setSpecCompFB(compNb=n, FB=FB, FB_frdm_prior='free')
        ##         struc.close()
        
        suffix = dict(instrumentNames)
        # suffix[len(suffix)] = ''
        if self.verbose>1:
            print 'suffix', suffix
        
        self.renormalize_parameters()
        
        # initialize parameters with NMF:
        # putting the HF0 from the SIMM model back in:
        #    lead instrument
        ##self.spec_comps[0]['factor'][0]['TW'][:-1] = (
        ##    self.simmModel.SIMMParams['HF00'])
        startincqt = np.sort(np.where(self.tft.time_stamps>=0)[0])[0]
        stopincqt = (
            startincqt + self.simmModel.SIMMParams['HF00'].shape[1])
        self.spec_comps[0][
            'factor'][0]['TW'][:-1, startincqt:stopincqt] = (
            self.simmModel.SIMMParams['HF00'])
        
        self.initialize_all_spec_comps_with_NMF(updateFreqBasis=False,
                                                niter=niter_nmf)
        # putting the HF0 from the SIMM model back in:
        #    lead instrument
        self.spec_comps[0][
            'factor'][0]['TW'][:-1, startincqt:stopincqt] = (
            self.simmModel.SIMMParams['HF00'])
        ##self.spec_comps[0]['factor'][0]['TW'][:-1] = (
        ##    self.simmModel.SIMMParams['HF00'])
        #        the following are too variable to be kept for now:
        #self.spec_comps[0]['factor'][1]['TW'][:-1] = (
        #    self.simmModel.SIMMParams['HPHI'])
        #self.spec_comps[0]['factor'][1]['FW'][:-1] = (
        #    self.simmModel.SIMMParams['HGAMMA'])
        #self.spec_comps[0]['factor'][1]['FB'][:-1] = (
        #    self.simmModel.SIMMParams['WGAMMA'])
        
        #    accompaniment: nothing for now.
        #    accompaniment: avoid or reduce effect of stuff in source 0, maybe:
        for j in range(1,self.nbComps-1):
            if instrumentNames[j] == 'SourceFilter':
                self.spec_comps[j]['factor'][0]['TW'][
                    :-1, startincqt:stopincqt] = 1.*(
                    self.simmModel.SIMMParams['HF00']==0)
        #    noise: nothing for now.
        
        ## 20130605T0104
        ##    Should we iterate a sequence of (estim_param_a_post_model, demix)
        ##    here? 
        
        # separate the files with these parameters:
        self.renormalize_parameters()
        self.separate_spat_comps(dir_results=dir_results,
                                 suffix=suffix)
        
        if self.verbose>1:
            print suffix
        
        # replace this with method:
        # run DEMIX on the separated files:
        ##estFiles = self.files['spat_comp']
        ##nbSources = len(self.spat_comps)
        ##if self.verbose>1:
        ##    print nbSources, "sources:", estFiles
        ##for nest, estfilename in enumerate(estFiles):
        ##    if self.verbose>1:
        ##        print estfilename
        ##    A = self.demixOnGivenFile(estfilename, nsources=1)
        ##    for r in range(self.rank[nest]):
        ##        self.spat_comps[nest]['params'][r][:,:] = (
        ##            A[0].T + 1e-3 * np.random.randn(*A[0].T.shape))
        ##
        ##self.renormalize_parameters()
        
        estFiles = self.initConvDemixOnSepSrc(suffix)
        
        self.separate_spatial_filter_comp(dir_results=dir_results,
                                          suffix=suffix)
        
        # Re-estimating all the parameters:
        logliks = self.estim_param_a_post_model()
        
        # Separate and Write them...
        if self.verbose:
            print "Writing files to", dir_results
            print self.files
        self.separate_spat_comps(dir_results=dir_results,
                                 suffix=suffix)
        return logliks
    
    def estimSIMM(self, maxFrames=4000, dir_results='tmp/', simmIterNum=30):
        """This method runs the SIMM estimation on the provided audio file.
        
        The lead source is assumed to be self.spec_comps[0]
        """

        ##numCompAccomp = (
        ##        np.sum([spec_comp['factor'][0]['FB'].shape[1]
        ##                for ncomp, spec_comp in self.spec_comps.items()])-
        ##        self.spec_comps[0]['factor'][0]['FB'].shape[1]
        ##        )
        numCompAccomp = 40 # TODO: check if this improves solo/acc separation
        if simmIterNum is None:
            simmIterNum = self.iter_num
        
        self.simmModel = SLS.SeparateLeadProcess(
            inputAudioFilename=self.audioObject.filename,
            stepNotes=self.sourceParams['stepnoteF0'],
            chirpPerF0=self.sourceParams['chirpPerF0'],
            nbIter=simmIterNum,
            windowSize=(
                self.sig_repr_params['wlen']/
                np.double(self.audioObject.samplerate)), # in seconds
            hopsize=self.sig_repr_params['hopsize'],
            NFT=self.sig_repr_params['fsize'],
            numCompAccomp=numCompAccomp,
            K_numFilters=self.nbFilterWeigs[0],
            P_numAtomFilters=self.nbFilterComps,
            #imageCanvas=canvas,
            minF0search=self.sourceParams['minF0search'],
            maxF0search=self.sourceParams['maxF0search'],
            minF0=self.sourceParams['minF0'],
            maxF0=self.sourceParams['maxF0'],
            verbose=self.verbose,
            tfrepresentation=self.sig_repr_params['transf'],
            cqtfmax=self.sig_repr_params['tffmax'],#4000,
            cqtfmin=self.sig_repr_params['tffmin'],#50,
            cqtbins=self.sig_repr_params['tfbpo'],#48,
            cqtWinFunc=self.sig_repr_params['tfWinFunc'],
            #slf.minqt.sqrt_blackmanharris,
            cqtAtomHopFactor=self.sig_repr_params['hopfactor'],#0.25,
            outputDirSuffix='tmp/', # dir_results,
            # this is not working, have to find a way
            initHF00='random',
            freeMemory=False)
        
        self.simmModel.autoMelSepAndWrite(maxFrames=maxFrames)
        
    def estimSUIMM(self, maxFrames=4000, **kwargs):
        """separates the audio signal into lead+accompaniment,
        including more noisy components for the lead than `self.estimSIMM`
        """
        if not hasattr(self, "simmModel"):
            self.estimSIMM(maxFrames=maxFrames, **kwargs)
            
        self.simmModel.estimStereoSUIMMParamsWriteSeps(maxFrames=maxFrames)
        
    
    def demixOnSepSIMM(self, unvoiced=True):
        """run DEMIX on the separated signals resulting from SIMM model
        """
        if not hasattr(self, 'simmModel'):
            self.estimSIMM()
            if unvoiced:
                self.estimSUIMM()
                
        if unvoiced:
            suffix = '_VUIMM'
        else:
            suffix = ''
        # DEMIX on lead instrument
        leadfilename = (
            self.simmModel.files['voc_output_file'][:-4] +
            suffix + '.wav')
        ALead = self.demixOnGivenFile(
            leadfilename,
            nsources=1)
        
        # DEMIX on accompaniment
        accpfilename = (
            self.simmModel.files['mus_output_file'][:-4] +
            suffix + '.wav')
        AAccp = self.demixOnGivenFile(
            accpfilename,
            nsources=self.nbComps-2)
        
        return ALead, AAccp
    
    def demixOnGivenFile(self, filename, nsources=1):
        '''running the DEMIX algorithm from :demix.DEMIX:
        
        '''
        maxclusters = 40
        neighbours = 15
        
        # default for demix to work best: #FIXME!!!
        #wlen = 2048
        #hopsize = 1024
        
        demixInst = demix.DEMIX(
            audio=filename,
            nsources=nsources, # spatial comps for demix
            #wlen=wlen,
            #hopsize=hopsize,
            #neighbors=neighbours,
            verbose=self.verbose,
            maxclusters=maxclusters,
            **self.demixParams)
            
        #demixInst.comp_pcafeatures()
        #demixInst.comp_parameters()
        #demixInst.init_subpts_set()
        demixInst.comp_clusters()
        demixInst.refine_clusters()
        
        # mixing parameters from DEMIX estimation:
        #     results in an nsrc x nfreqs x nc array
        A = demixInst.steeringVectorsFromCentroids()
        del demixInst
        if A.size == 0:
            warnMsg = "There are no clusters in demix, returning dummy matrix."
            warnings.warn(warnMsg)
            if self.verbose:
                print warnMsg
            return np.cos(0.25 * np.pi) * np.ones([nsources,
                                                   A.shape[1], A.shape[2]])
        return A
    
    def initConvDemixOnSepSrc(self, suffix):
        """initialize the convolutive parameters with DEMIX, running on each of
        the separated sources
        """
        if not hasattr(self, "files"):
            warnings.warn("The sources were not separated, compute them first"+
                          " with separate_spat_comps.")
            return None
        estFiles = self.files['spat_comp']
        nbSources = len(self.spat_comps)
        if self.verbose>1:
            print nbSources, "sources:", estFiles
        for nest, estfilename in enumerate(estFiles):
            if self.verbose>1:
                print estfilename
            A = self.demixOnGivenFile(estfilename, nsources=1)
            for r in range(self.rank[nest]):
                self.spat_comps[nest]['params'][r][:,:] = (
                    A[0].T + 1e-3 * np.random.randn(*A[0].T.shape))
        
        self.renormalize_parameters()
        
        return estFiles
    
